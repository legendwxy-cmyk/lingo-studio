import Foundation
import XCTest
@testable import LingoReelCore

final class CoreTests: XCTestCase {
    private var tmpDir: URL!

    override func setUpWithError() throws {
        tmpDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("lingoreel_xctest_\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        if let tmpDir {
            try? FileManager.default.removeItem(at: tmpDir)
        }
    }

    func testDesktopConfigRoundTripAndPortClamping() throws {
        let store = ConfigStore(configURL: tmpDir.appendingPathComponent("desktop_config.json"))
        // Missing file returns clean defaults
        let defaults = store.load()
        XCTAssertEqual(defaults.port, 8000)
        XCTAssertFalse(defaults.lanAccess)
        XCTAssertTrue(defaults.hfMirror)

        // Valid custom values persist cleanly
        let custom = DesktopConfig(
            port: 8899,
            lanAccess: true,
            accessPassword: "secret-pass",
            hfMirror: false,
            autoStartService: true
        )
        try store.save(custom)
        let loaded = store.load()
        XCTAssertEqual(loaded, custom)

        // Partial legacy JSON (e.g. from older v1.1.1) must preserve existing keys without failing
        let legacyJSON = #"{"port": 8765, "lan_access": true}"#
        try legacyJSON.write(to: tmpDir.appendingPathComponent("desktop_config.json"), atomically: true, encoding: .utf8)
        let partial = store.load()
        XCTAssertEqual(partial.port, 8765)
        XCTAssertTrue(partial.lanAccess)
        XCTAssertTrue(partial.hfMirror)
        XCTAssertFalse(partial.autoStartService)

        // Out-of-range ports clamp back to 8000
        XCTAssertEqual(DesktopConfig.clampPort(80), 8000)
        XCTAssertEqual(DesktopConfig.clampPort(70000), 8000)
        XCTAssertEqual(DesktopConfig.clampPort(1024), 1024)
        XCTAssertEqual(DesktopConfig.clampPort(65535), 65535)
    }

    func testSQLiteSettingsStoreMaskingAndPreservation() throws {
        let dbURL = tmpDir.appendingPathComponent("lexifilm.db")
        let store = SettingsStore(dbURL: dbURL)

        let initial = try store.loadPublicSettings()
        XCTAssertFalse(initial.hasLLMKey)
        XCTAssertFalse(initial.hasASRKey)
        XCTAssertEqual(initial.asrMode, "auto")

        // Save raw keys -> public read returns masked keys
        var draft = initial
        draft.llmBaseURL = "https://api.deepseek.com/v1"
        draft.llmModel = "deepseek-chat"
        draft.llmAPIKey = "sk-deepseek-1234567890abcd"
        draft.asrAPIKey = "sk-asr-9876543210wxyz"
        let pub = try store.saveSettings(draft)

        XCTAssertTrue(pub.hasLLMKey)
        XCTAssertTrue(pub.hasASRKey)
        XCTAssertEqual(pub.llmAPIKey, "sk-••••abcd")
        XCTAssertEqual(pub.asrAPIKey, "sk-••••wxyz")
        XCTAssertTrue(SecretMasker.isMasked(pub.llmAPIKey))

        // Re-saving with masked key MUST preserve raw key in DB
        var draft2 = pub
        draft2.llmModel = "deepseek-reasoner"
        let pub2 = try store.saveSettings(draft2)
        XCTAssertTrue(pub2.hasLLMKey)
        let rawAfter = try store.readRawDictionary()
        XCTAssertEqual(rawAfter["llm_api_key"], "sk-deepseek-1234567890abcd")
        XCTAssertEqual(rawAfter["asr_api_key"], "sk-asr-9876543210wxyz")
        XCTAssertEqual(rawAfter["llm_model"], "deepseek-reasoner")

        // Resolving effective key with empty/masked input falls back to stored raw secret only when allowed
        XCTAssertEqual(store.resolveEffectiveLLMKey(inputKey: ""), "sk-deepseek-1234567890abcd")
        XCTAssertEqual(store.resolveEffectiveLLMKey(inputKey: "sk-••••abcd"), "sk-deepseek-1234567890abcd")
        XCTAssertEqual(store.resolveEffectiveLLMKey(inputKey: "", allowStoredFallback: false), "")
        XCTAssertEqual(store.resolveEffectiveLLMKey(inputKey: "sk-••••abcd", allowStoredFallback: false), "")
        XCTAssertEqual(store.resolveEffectiveLLMKey(inputKey: "sk-new-override-key"), "sk-new-override-key")

        // Explicit clear wipes only the targeted secret
        let pub3 = try store.saveSettings(pub2, clearLLMKey: true, clearASRKey: false)
        XCTAssertFalse(pub3.hasLLMKey)
        XCTAssertTrue(pub3.hasASRKey)
        let rawAfterClear = try store.readRawDictionary()
        XCTAssertEqual(rawAfterClear["llm_api_key"], "")
        XCTAssertEqual(rawAfterClear["asr_api_key"], "sk-asr-9876543210wxyz")
    }

    func testProviderPresetsPreserveCustomASRForLLMOnlyVendors() {
        var settings = EngineSettings(from: [:])
        settings.asrBaseURL = "https://custom-asr.example.com/v1"
        settings.asrModel = "custom-whisper"

        for llmOnlyID in ["deepseek", "qwen", "gemini"] {
            let preset = try! XCTUnwrap(ProviderPreset.all.first(where: { $0.id == llmOnlyID }))
            preset.apply(to: &settings)
            XCTAssertEqual(settings.asrBaseURL, "https://custom-asr.example.com/v1", "\(llmOnlyID) must preserve asrBaseURL")
            XCTAssertEqual(settings.asrModel, "custom-whisper", "\(llmOnlyID) must preserve asrModel")
        }

        let groq = try! XCTUnwrap(ProviderPreset.all.first(where: { $0.id == "groq" }))
        groq.apply(to: &settings)
        XCTAssertEqual(settings.asrBaseURL, "https://api.groq.com/openai/v1")
        XCTAssertEqual(settings.asrModel, "whisper-large-v3-turbo")
    }

    func testEndpointURLBuilderPreventsDoubleSuffix() {
        XCTAssertEqual(
            EndpointURLBuilder.chatCompletionsURL(from: "https://api.deepseek.com/v1/"),
            "https://api.deepseek.com/v1/chat/completions"
        )
        XCTAssertEqual(
            EndpointURLBuilder.chatCompletionsURL(from: "https://api.deepseek.com/v1/chat/completions"),
            "https://api.deepseek.com/v1/chat/completions"
        )
        XCTAssertEqual(
            EndpointURLBuilder.audioTranscriptionsURL(from: "https://api.openai.com/v1"),
            "https://api.openai.com/v1/audio/transcriptions"
        )
        XCTAssertEqual(
            EndpointURLBuilder.audioTranscriptionsURL(from: "https://api.openai.com/v1/audio/transcriptions/"),
            "https://api.openai.com/v1/audio/transcriptions"
        )
    }

    func testPythonVersionValidationAndEnvironmentProbe() {
        XCTAssertTrue(EnvironmentManager.isSupportedPythonVersion("3.10.0"))
        XCTAssertTrue(EnvironmentManager.isSupportedPythonVersion("3.11.9"))
        XCTAssertTrue(EnvironmentManager.isSupportedPythonVersion("3.12.7"))
        XCTAssertFalse(EnvironmentManager.isSupportedPythonVersion("3.9.18"))
        XCTAssertFalse(EnvironmentManager.isSupportedPythonVersion("3.13.0"))
        XCTAssertFalse(EnvironmentManager.isSupportedPythonVersion("4.0.0"))
        XCTAssertFalse(EnvironmentManager.isSupportedPythonVersion("3.8.18"))
        XCTAssertFalse(EnvironmentManager.isSupportedPythonVersion("2.7.18"))
        XCTAssertFalse(EnvironmentManager.isSupportedPythonVersion("invalid"))

        let paths = AppPaths(
            appResourcesDir: tmpDir,
            dataDir: tmpDir.appendingPathComponent("data"),
            venvDir: tmpDir.appendingPathComponent(".venv")
        )
        XCTAssertEqual(paths.whisperCacheDir.lastPathComponent, "whisper-cache")
        let mgr = EnvironmentManager(paths: paths)
        let report = mgr.inspectEnvironment()
        XCTAssertEqual(report.items.count, 5)
        XCTAssertFalse(report.venvReady)
        XCTAssertFalse(report.coreReady)
    }

    func testDatabaseStatsOnFreshDB() {
        let store = SettingsStore(dbURL: tmpDir.appendingPathComponent("empty.db"))
        let stats = store.readDatabaseStats()
        XCTAssertEqual(stats.episodeCount, 0)
        XCTAssertEqual(stats.vocabCount, 0)
    }

    func testLANIPv4SelectionIgnoresVPNAndFakeIP() {
        let withClashAndWiFi = [
            (iface: "lo0", ip: "127.0.0.1"),
            (iface: "utun0", ip: "198.18.0.1"),
            (iface: "utun3", ip: "100.64.0.12"),
            (iface: "awdl0", ip: "169.254.12.34"),
            (iface: "en5", ip: "192.168.1.99"),
            (iface: "en0", ip: "192.168.1.28"),
        ]
        XCTAssertEqual(NetworkUtils.selectBestLANIPv4(from: withClashAndWiFi), "192.168.1.28")

        let usbEthernetOnly = [
            (iface: "utun0", ip: "198.18.0.1"),
            (iface: "en6", ip: "10.0.0.42"),
        ]
        XCTAssertEqual(NetworkUtils.selectBestLANIPv4(from: usbEthernetOnly), "10.0.0.42")

        let offlineOnly = [
            (iface: "lo0", ip: "127.0.0.1"),
            (iface: "en0", ip: "169.254.1.2"),
            (iface: "utun0", ip: "198.18.0.1"),
        ]
        XCTAssertNil(NetworkUtils.selectBestLANIPv4(from: offlineOnly))
    }
}

