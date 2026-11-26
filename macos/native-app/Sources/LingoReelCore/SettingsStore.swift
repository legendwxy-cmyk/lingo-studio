import Foundation
import SQLite3

private let sqliteTransient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

public enum SettingsStoreError: LocalizedError {
    case openFailed(String)
    case queryFailed(String)

    public var errorDescription: String? {
        switch self {
        case .openFailed(let msg): return "无法打开本地数据库：\(msg)"
        case .queryFailed(let msg): return "数据库读写失败：\(msg)"
        }
    }
}

/// Thread-safe native SQLite reader/writer sharing lexifilm.db with the FastAPI backend.
public final class SettingsStore: Sendable {
    public let dbURL: URL

    public init(dbURL: URL) {
        self.dbURL = dbURL
    }

    private func withConnection<T>(_ body: (OpaquePointer) throws -> T) throws -> T {
        let dir = dbURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        var db: OpaquePointer?
        let rc = sqlite3_open_v2(
            dbURL.path,
            &db,
            SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX,
            nil
        )
        guard rc == SQLITE_OK, let handle = db else {
            let err = db.flatMap { String(cString: sqlite3_errmsg($0)) } ?? "code \(rc)"
            if let db { sqlite3_close(db) }
            throw SettingsStoreError.openFailed(err)
        }
        defer { sqlite3_close(handle) }

        sqlite3_busy_timeout(handle, 15_000)
        sqlite3_exec(handle, "PRAGMA journal_mode=WAL;", nil, nil, nil)
        return try body(handle)
    }

    private func ensureSettingsTable(_ db: OpaquePointer) throws {
        let createSQL = "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        if sqlite3_exec(db, createSQL, nil, nil, nil) != SQLITE_OK {
            throw SettingsStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
        }
        let insertSQL = "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, insertSQL, -1, &stmt, nil) == SQLITE_OK, let s = stmt else {
            throw SettingsStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
        }
        defer { sqlite3_finalize(s) }

        for (k, v) in LingoReelConstants.defaultEngineSettings {
            sqlite3_reset(s)
            sqlite3_clear_bindings(s)
            sqlite3_bind_text(s, 1, k, -1, sqliteTransient)
            sqlite3_bind_text(s, 2, v, -1, sqliteTransient)
            sqlite3_step(s)
        }
    }

    public func readRawDictionary() throws -> [String: String] {
        try withConnection { db in
            try ensureSettingsTable(db)
            var result = LingoReelConstants.defaultEngineSettings
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, "SELECT key, value FROM settings;", -1, &stmt, nil) == SQLITE_OK,
                  let s = stmt
            else {
                throw SettingsStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
            }
            defer { sqlite3_finalize(s) }

            while sqlite3_step(s) == SQLITE_ROW {
                if let cKey = sqlite3_column_text(s, 0), let cVal = sqlite3_column_text(s, 1) {
                    result[String(cString: cKey)] = String(cString: cVal)
                }
            }
            return result
        }
    }

    /// Loads settings with secrets masked (`sk-••••xxxx`) for safe UI binding.
    public func loadPublicSettings() throws -> EngineSettings {
        var raw = try readRawDictionary()
        let hasLLM = !(raw["llm_api_key"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let hasASR = !(raw["asr_api_key"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        if hasLLM { raw["llm_api_key"] = SecretMasker.mask(raw["llm_api_key"] ?? "") }
        if hasASR { raw["asr_api_key"] = SecretMasker.mask(raw["asr_api_key"] ?? "") }
        return EngineSettings(from: raw, hasLLMKey: hasLLM, hasASRKey: hasASR)
    }

    /// Saves settings while preserving stored secret keys when UI sends a masked placeholder (`••••`).
    /// Pass `clearLLMKey: true` / `clearASRKey: true` to explicitly wipe a stored key.
    public func saveSettings(
        _ settings: EngineSettings,
        clearLLMKey: Bool = false,
        clearASRKey: Bool = false
    ) throws -> EngineSettings {
        let updates = settings.toDictionary()
        try withConnection { db in
            try ensureSettingsTable(db)
            let sql = """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let s = stmt else {
                throw SettingsStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
            }
            defer { sqlite3_finalize(s) }

            for (key, value) in updates {
                if key == "llm_api_key" {
                    if clearLLMKey {
                        // write empty
                    } else if SecretMasker.isMasked(value) {
                        continue
                    }
                }
                if key == "asr_api_key" {
                    if clearASRKey {
                        // write empty
                    } else if SecretMasker.isMasked(value) {
                        continue
                    }
                }
                let finalVal: String
                if (key == "llm_api_key" && clearLLMKey) || (key == "asr_api_key" && clearASRKey) {
                    finalVal = ""
                } else {
                    finalVal = value
                }
                sqlite3_reset(s)
                sqlite3_clear_bindings(s)
                sqlite3_bind_text(s, 1, key, -1, sqliteTransient)
                sqlite3_bind_text(s, 2, finalVal, -1, sqliteTransient)
                if sqlite3_step(s) != SQLITE_DONE {
                    throw SettingsStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
                }
            }
        }
        return try loadPublicSettings()
    }

    /// Resolves effective raw API key (if the user typed a new raw key use it; if masked/empty use stored raw key when allowed).
    public func resolveEffectiveLLMKey(inputKey: String, allowStoredFallback: Bool = true) -> String {
        let trimmed = inputKey.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty && !SecretMasker.isMasked(trimmed) {
            return trimmed
        }
        guard allowStoredFallback else {
            return ""
        }
        return (try? readRawDictionary()["llm_api_key"]?.trimmingCharacters(in: .whitespacesAndNewlines)) ?? ""
    }

    /// Safely counts episodes & bookmarked vocabulary entries even before backend initializes those tables.
    public func readDatabaseStats() -> DatabaseStats {
        guard FileManager.default.fileExists(atPath: dbURL.path) else {
            return DatabaseStats(episodeCount: 0, vocabCount: 0)
        }
        do {
            return try withConnection { db in
                let epCount = querySingleInt(db, "SELECT COUNT(*) FROM episodes;")
                let vocabCount = querySingleInt(db, "SELECT COUNT(*) FROM entries WHERE is_bookmarked = 1;")
                return DatabaseStats(episodeCount: epCount, vocabCount: vocabCount)
            }
        } catch {
            return DatabaseStats(episodeCount: 0, vocabCount: 0)
        }
    }

    private func querySingleInt(_ db: OpaquePointer, _ sql: String) -> Int {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let s = stmt else {
            return 0
        }
        defer { sqlite3_finalize(s) }
        if sqlite3_step(s) == SQLITE_ROW {
            return Int(sqlite3_column_int(s, 0))
        }
        return 0
    }
}
