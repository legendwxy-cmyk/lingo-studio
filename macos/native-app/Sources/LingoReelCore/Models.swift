import Foundation
#if canImport(Darwin)
import Darwin
#endif

public enum LingoReelConstants {
    public static let secretMaskMarker = "••••"
    public static let defaultPort = 8000
    public static let minPort = 1024
    public static let maxPort = 65535
    public static let hfMirrorURL = "https://hf-mirror.com"
    public static let tsinghuaPyPIURL = "https://pypi.tuna.tsinghua.edu.cn/simple"
    public static let bundleIdentifier = "com.lingoreel.studio"

    public static let defaultEngineSettings: [String: String] = [
        "asr_mode": "auto",
        "asr_base_url": "https://api.openai.com/v1",
        "asr_api_key": "",
        "asr_model": "whisper-1",
        "local_whisper_model": "tiny.en",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_api_key": "",
        "llm_model": "gpt-4o-mini",
        "default_target_lang": "zh-CN",
        "enable_online_dict_fallback": "true",
    ]
}

public struct DesktopConfig: Codable, Equatable, Sendable {
    public var port: Int
    public var lanAccess: Bool
    public var accessPassword: String
    public var hfMirror: Bool
    public var autoStartService: Bool

    enum CodingKeys: String, CodingKey {
        case port
        case lanAccess = "lan_access"
        case accessPassword = "access_password"
        case hfMirror = "hf_mirror"
        case autoStartService = "auto_start_service"
    }

    public init(
        port: Int = LingoReelConstants.defaultPort,
        lanAccess: Bool = false,
        accessPassword: String = "",
        hfMirror: Bool = true,
        autoStartService: Bool = false
    ) {
        self.port = Self.clampPort(port)
        self.lanAccess = lanAccess
        self.accessPassword = accessPassword
        self.hfMirror = hfMirror
        self.autoStartService = autoStartService
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let rawPort = try c.decodeIfPresent(Int.self, forKey: .port) ?? LingoReelConstants.defaultPort
        self.port = Self.clampPort(rawPort)
        self.lanAccess = try c.decodeIfPresent(Bool.self, forKey: .lanAccess) ?? false
        self.accessPassword = try c.decodeIfPresent(String.self, forKey: .accessPassword) ?? ""
        self.hfMirror = try c.decodeIfPresent(Bool.self, forKey: .hfMirror) ?? true
        self.autoStartService = try c.decodeIfPresent(Bool.self, forKey: .autoStartService) ?? false
    }

    public static func clampPort(_ p: Int) -> Int {
        if p < LingoReelConstants.minPort || p > LingoReelConstants.maxPort {
            return LingoReelConstants.defaultPort
        }
        return p
    }
}

public struct EngineSettings: Equatable, Sendable {
    public var asrMode: String
    public var asrBaseURL: String
    public var asrAPIKey: String
    public var asrModel: String
    public var localWhisperModel: String
    public var llmBaseURL: String
    public var llmAPIKey: String
    public var llmModel: String
    public var defaultTargetLang: String
    public var enableOnlineDictFallback: Bool

    public var hasLLMKey: Bool
    public var hasASRKey: Bool

    public init(from dict: [String: String], hasLLMKey: Bool? = nil, hasASRKey: Bool? = nil) {
        let d = LingoReelConstants.defaultEngineSettings.merging(dict) { _, new in new }
        self.asrMode = d["asr_mode"] ?? "auto"
        self.asrBaseURL = d["asr_base_url"] ?? "https://api.openai.com/v1"
        self.asrAPIKey = d["asr_api_key"] ?? ""
        self.asrModel = d["asr_model"] ?? "whisper-1"
        self.localWhisperModel = d["local_whisper_model"] ?? "tiny.en"
        self.llmBaseURL = d["llm_base_url"] ?? "https://api.openai.com/v1"
        self.llmAPIKey = d["llm_api_key"] ?? ""
        self.llmModel = d["llm_model"] ?? "gpt-4o-mini"
        self.defaultTargetLang = d["default_target_lang"] ?? "zh-CN"
        self.enableOnlineDictFallback = (d["enable_online_dict_fallback"] ?? "true").lowercased() != "false"
        self.hasLLMKey = hasLLMKey ?? !self.llmAPIKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        self.hasASRKey = hasASRKey ?? !self.asrAPIKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public func toDictionary() -> [String: String] {
        [
            "asr_mode": asrMode,
            "asr_base_url": asrBaseURL.trimmingCharacters(in: .whitespacesAndNewlines),
            "asr_api_key": asrAPIKey.trimmingCharacters(in: .whitespacesAndNewlines),
            "asr_model": asrModel.trimmingCharacters(in: .whitespacesAndNewlines),
            "local_whisper_model": localWhisperModel,
            "llm_base_url": llmBaseURL.trimmingCharacters(in: .whitespacesAndNewlines),
            "llm_api_key": llmAPIKey.trimmingCharacters(in: .whitespacesAndNewlines),
            "llm_model": llmModel.trimmingCharacters(in: .whitespacesAndNewlines),
            "default_target_lang": defaultTargetLang,
            "enable_online_dict_fallback": enableOnlineDictFallback ? "true" : "false",
        ]
    }
}

public struct ProviderPreset: Identifiable, Equatable, Sendable {
    public let id: String
    public let label: String
    public let llmBaseURL: String
    public let llmModel: String
    /// Nil for LLM-only providers so user's existing ASR endpoint is preserved.
    public let asrBaseURL: String?
    public let asrModel: String?

    public static let all: [ProviderPreset] = [
        ProviderPreset(
            id: "deepseek",
            label: "DeepSeek",
            llmBaseURL: "https://api.deepseek.com/v1",
            llmModel: "deepseek-chat",
            asrBaseURL: nil,
            asrModel: nil
        ),
        ProviderPreset(
            id: "openai",
            label: "OpenAI",
            llmBaseURL: "https://api.openai.com/v1",
            llmModel: "gpt-4o-mini",
            asrBaseURL: "https://api.openai.com/v1",
            asrModel: "whisper-1"
        ),
        ProviderPreset(
            id: "qwen",
            label: "通义千问",
            llmBaseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            llmModel: "qwen-plus",
            asrBaseURL: nil,
            asrModel: nil
        ),
        ProviderPreset(
            id: "groq",
            label: "Groq Whisper",
            llmBaseURL: "https://api.groq.com/openai/v1",
            llmModel: "llama-3.3-70b-versatile",
            asrBaseURL: "https://api.groq.com/openai/v1",
            asrModel: "whisper-large-v3-turbo"
        ),
        ProviderPreset(
            id: "siliconflow",
            label: "硅基流动",
            llmBaseURL: "https://api.siliconflow.cn/v1",
            llmModel: "Qwen/Qwen2.5-7B-Instruct",
            asrBaseURL: "https://api.siliconflow.cn/v1",
            asrModel: "FunAudioLLM/SenseVoiceSmall"
        ),
        ProviderPreset(
            id: "gemini",
            label: "Gemini 兼容",
            llmBaseURL: "https://generativelanguage.googleapis.com/v1beta/openai",
            llmModel: "gemini-2.5-flash",
            asrBaseURL: nil,
            asrModel: nil
        ),
    ]

    public func apply(to settings: inout EngineSettings) {
        settings.llmBaseURL = llmBaseURL
        settings.llmModel = llmModel
        if let asrBase = asrBaseURL {
            settings.asrBaseURL = asrBase
        }
        if let asrM = asrModel {
            settings.asrModel = asrM
        }
    }
}

public enum SecretMasker {
    public static func mask(_ raw: String) -> String {
        let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.isEmpty { return "" }
        if s.count <= 8 { return LingoReelConstants.secretMaskMarker }
        let prefix = s.prefix(3)
        let suffix = s.suffix(4)
        return "\(prefix)\(LingoReelConstants.secretMaskMarker)\(suffix)"
    }

    public static func isMasked(_ value: String?) -> Bool {
        guard let value = value else { return false }
        return value.contains(LingoReelConstants.secretMaskMarker)
    }
}

public enum EndpointURLBuilder {
    public static func chatCompletionsURL(from baseURL: String) -> String {
        var clean = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if clean.isEmpty {
            clean = "https://api.openai.com/v1"
        }
        while clean.hasSuffix("/") {
            clean.removeLast()
        }
        if clean.hasSuffix("/chat/completions") {
            return clean
        }
        return "\(clean)/chat/completions"
    }

    public static func audioTranscriptionsURL(from baseURL: String) -> String {
        var clean = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if clean.isEmpty {
            clean = "https://api.openai.com/v1"
        }
        while clean.hasSuffix("/") {
            clean.removeLast()
        }
        if clean.hasSuffix("/audio/transcriptions") {
            return clean
        }
        return "\(clean)/audio/transcriptions"
    }
}

public struct DependencyItem: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let detail: String
    public let required: Bool
    public let installed: Bool
    public let version: String
    public let path: String

    public init(
        id: String,
        title: String,
        detail: String,
        required: Bool,
        installed: Bool,
        version: String = "",
        path: String = ""
    ) {
        self.id = id
        self.title = title
        self.detail = detail
        self.required = required
        self.installed = installed
        self.version = version
        self.path = path
    }
}

public struct EnvironmentReport: Equatable, Sendable {
    public var pythonPath: String?
    public var pythonVersion: String
    public var venvReady: Bool
    public var ffmpegPath: String?
    public var items: [DependencyItem]
    public var coreReady: Bool
    public var allReady: Bool
    public var checkedAt: Date

    public static let empty = EnvironmentReport(
        pythonPath: nil,
        pythonVersion: "",
        venvReady: false,
        ffmpegPath: nil,
        items: [],
        coreReady: false,
        allReady: false,
        checkedAt: Date()
    )
}

public struct DatabaseStats: Equatable, Sendable {
    public let episodeCount: Int
    public let vocabCount: Int
}

public struct LLMTestResult: Equatable, Sendable {
    public let ok: Bool
    public let message: String
    public let latencyMs: Int?
    public let replyPreview: String
}

public struct AppPaths: Sendable {
    public let appResourcesDir: URL
    public let backendDir: URL
    public let frontendDistDir: URL
    public let appSupportDir: URL
    public let dataDir: URL
    public let venvDir: URL
    public let whisperCacheDir: URL
    public let dbPath: URL
    public let configPath: URL
    public let logFilePath: URL

    public init(
        appResourcesDir: URL,
        dataDir: URL,
        venvDir: URL,
        appSupportDir: URL? = nil,
        whisperCacheDir: URL? = nil
    ) {
        self.appResourcesDir = appResourcesDir
        self.backendDir = appResourcesDir.appendingPathComponent("backend", isDirectory: true)
        self.frontendDistDir = appResourcesDir
            .appendingPathComponent("frontend", isDirectory: true)
            .appendingPathComponent("dist", isDirectory: true)
        let resolvedSupport = appSupportDir ?? dataDir.deletingLastPathComponent()
        self.appSupportDir = resolvedSupport
        self.dataDir = dataDir
        self.venvDir = venvDir
        self.whisperCacheDir = whisperCacheDir
            ?? resolvedSupport.appendingPathComponent("whisper-cache", isDirectory: true)
        self.dbPath = dataDir.appendingPathComponent("lexifilm.db")
        self.configPath = dataDir.appendingPathComponent("desktop_config.json")
        self.logFilePath = dataDir.appendingPathComponent("app.log")
    }

    public static func resolveDefault() -> AppPaths {
        let env = ProcessInfo.processInfo.environment
        let fm = FileManager.default
        let home = fm.homeDirectoryForCurrentUser

        let defaultSupportDir = home
            .appendingPathComponent("Library", isDirectory: true)
            .appendingPathComponent("Application Support", isDirectory: true)
            .appendingPathComponent("LingoReelStudio", isDirectory: true)

        let dataDir: URL
        if let customData = env["LINGOREEL_DATA_DIR"], !customData.isEmpty {
            dataDir = URL(fileURLWithPath: (customData as NSString).expandingTildeInPath, isDirectory: true)
        } else {
            dataDir = defaultSupportDir.appendingPathComponent("data", isDirectory: true)
        }

        let venvDir: URL
        if let customVenv = env["LINGOREEL_VENV_DIR"], !customVenv.isEmpty {
            venvDir = URL(fileURLWithPath: (customVenv as NSString).expandingTildeInPath, isDirectory: true)
        } else {
            venvDir = defaultSupportDir.appendingPathComponent(".venv", isDirectory: true)
        }

        let whisperCacheDir: URL
        if let customHF = env["HF_HOME"], !customHF.isEmpty {
            whisperCacheDir = URL(fileURLWithPath: (customHF as NSString).expandingTildeInPath, isDirectory: true)
        } else {
            whisperCacheDir = defaultSupportDir.appendingPathComponent("whisper-cache", isDirectory: true)
        }

        // Locate bundled app/ directory: Contents/Resources/app inside .app bundle, or dev repo fallback
        var candidates: [URL] = []
        if let customApp = env["LINGOREEL_APP_DIR"], !customApp.isEmpty {
            candidates.append(URL(fileURLWithPath: customApp, isDirectory: true))
        }
        if let resURL = Bundle.main.resourceURL {
            candidates.append(resURL.appendingPathComponent("app", isDirectory: true))
        }
        let execDir = URL(fileURLWithPath: CommandLine.arguments.first ?? ".").deletingLastPathComponent()
        candidates.append(execDir.appendingPathComponent("../Resources/app", isDirectory: true).standardizedFileURL)
        candidates.append(URL(fileURLWithPath: fm.currentDirectoryPath, isDirectory: true))

        var chosen = candidates.first ?? URL(fileURLWithPath: fm.currentDirectoryPath, isDirectory: true)
        for cand in candidates {
            let mainPy = cand.appendingPathComponent("backend/main.py").path
            if fm.fileExists(atPath: mainPy) {
                chosen = cand
                break
            }
        }

        return AppPaths(
            appResourcesDir: chosen,
            dataDir: dataDir,
            venvDir: venvDir,
            appSupportDir: defaultSupportDir,
            whisperCacheDir: whisperCacheDir
        )
    }
}

public enum NetworkUtils {
    public static func isPrivateLANIPv4(_ ip: String) -> Bool {
        let parts = ip.split(separator: ".").compactMap { Int($0) }
        guard parts.count == 4 else { return false }
        if parts[0] == 10 { return true }
        if parts[0] == 192 && parts[1] == 168 { return true }
        if parts[0] == 172 && (16...31).contains(parts[1]) { return true }
        return false
    }

    /// Picks the most suitable LAN IPv4 from interface candidates, preferring physical Wi-Fi/Ethernet
    /// RFC1918 addresses and ignoring loopback, link-local, Clash/VPN fake-IP (198.18/19), and virtual utun/awdl interfaces.
    public static func selectBestLANIPv4(from candidates: [(iface: String, ip: String)]) -> String? {
        let virtualPrefixes = ["lo", "utun", "awdl", "llw", "bridge", "ap", "anpi", "gif", "stf", "ipsec", "ppp"]
        var bestIP: String?
        var bestScore = Int.min

        for item in candidates {
            let ip = item.ip.trimmingCharacters(in: .whitespacesAndNewlines)
            let name = item.iface.lowercased()
            if ip.isEmpty || ip.hasPrefix("127.") || ip.hasPrefix("169.254.") || ip.hasPrefix("198.18.") || ip.hasPrefix("198.19.") {
                continue
            }
            let isVirtual = virtualPrefixes.contains { name.hasPrefix($0) }
            let isPrivate = isPrivateLANIPv4(ip)
            var score = 0
            if name == "en0" {
                score += 100
            } else if name == "en1" {
                score += 90
            } else if name.hasPrefix("en") || name.hasPrefix("eth") || name.hasPrefix("wlan") {
                score += 70
            } else if isVirtual {
                score -= 100
            } else {
                score += 20
            }
            if isPrivate {
                score += 50
            }
            if score > bestScore {
                bestScore = score
                bestIP = ip
            }
        }
        return bestIP
    }

    /// Returns the primary local IPv4 address (e.g. 192.168.x.x) if connected to a LAN.
    public static func detectLANIPv4() -> String? {
        #if canImport(Darwin)
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0, let first = ifaddr else { return nil }
        defer { freeifaddrs(ifaddr) }

        var candidates: [(iface: String, ip: String)] = []
        var ptr: UnsafeMutablePointer<ifaddrs>? = first
        while let current = ptr {
            let flags = Int32(current.pointee.ifa_flags)
            let isUp = (flags & (IFF_UP | IFF_RUNNING)) == (IFF_UP | IFF_RUNNING)
            let isLoopback = (flags & IFF_LOOPBACK) != 0
            if isUp && !isLoopback, let addr = current.pointee.ifa_addr, addr.pointee.sa_family == UInt8(AF_INET) {
                var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                if getnameinfo(
                    addr,
                    socklen_t(addr.pointee.sa_len),
                    &host,
                    socklen_t(host.count),
                    nil,
                    0,
                    NI_NUMERICHOST
                ) == 0 {
                    let ip = String(cString: host)
                    let name = String(cString: current.pointee.ifa_name)
                    candidates.append((iface: name, ip: ip))
                }
            }
            ptr = current.pointee.ifa_next
        }
        return selectBestLANIPv4(from: candidates)
        #else
        return nil
        #endif
    }
}

