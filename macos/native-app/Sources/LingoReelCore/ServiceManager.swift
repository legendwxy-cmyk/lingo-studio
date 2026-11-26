import Combine
import Foundation
#if canImport(Darwin)
import Darwin
#endif

public struct LogEntry: Identifiable, Equatable, Sendable {
    public let id = UUID()
    public let timestamp: String
    public let line: String

    public init(timestamp: String, line: String) {
        self.timestamp = timestamp
        self.line = line
    }
}

/// Central observable controller managing the FastAPI backend lifecycle, native SQLite settings,
/// environment checks, dependency installation, live log streaming, and health polling.
@MainActor
public final class ServiceManager: ObservableObject {
    public let paths: AppPaths
    public let configStore: ConfigStore
    public let settingsStore: SettingsStore
    public let envManager: EnvironmentManager

    @Published public var config: DesktopConfig
    @Published public var engineSettings: EngineSettings
    @Published public var envReport: EnvironmentReport = .empty
    @Published public var dbStats: DatabaseStats = DatabaseStats(episodeCount: 0, vocabCount: 0)

    @Published public var isRunning: Bool = false
    @Published public var isHealthy: Bool = false
    @Published public var isStarting: Bool = false
    @Published public var isInstalling: Bool = false
    @Published public var isCheckingEnv: Bool = false
    @Published public var isTestingLLM: Bool = false

    @Published public var pid: Int32? = nil
    @Published public var activePort: Int? = nil
    @Published public var activeLanAccess: Bool = false
    @Published public var startedAt: Date? = nil
    @Published public var uptimeText: String = "00:00"
    @Published public var lanIP: String? = nil

    @Published public var logs: [LogEntry] = []
    @Published public var toastMessage: String = ""
    @Published public var toastIsError: Bool = false
    @Published public var llmTestResult: LLMTestResult? = nil
    @Published public var lastErrorBanner: String = ""

    private var backendProcess: Process?
    private var logFileHandle: FileHandle?
    private var pollTimer: Timer?
    private var toastTask: Task<Void, Never>?
    private var stoppingIntentionally: Bool = false
    private let maxLogEntries = 800

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()

    public init(paths: AppPaths = .resolveDefault()) {
        self.paths = paths
        self.configStore = ConfigStore(configURL: paths.configPath)
        self.settingsStore = SettingsStore(dbURL: paths.dbPath)
        self.envManager = EnvironmentManager(paths: paths)

        try? FileManager.default.createDirectory(at: paths.dataDir, withIntermediateDirectories: true)

        let loadedConfig = configStore.load()
        self.config = loadedConfig
        self.engineSettings = (try? settingsStore.loadPublicSettings())
            ?? EngineSettings(from: LingoReelConstants.defaultEngineSettings)
        self.lanIP = NetworkUtils.detectLANIPv4()
        self.dbStats = settingsStore.readDatabaseStats()

        prepareLogFile()
        appendLog("Lingo 原生 SwiftUI 桌面控制台已启动（数据目录：\(paths.dataDir.path)）")
    }

    public var effectivePort: Int {
        isRunning ? (activePort ?? config.port) : config.port
    }

    public var localURL: URL {
        URL(string: "http://127.0.0.1:\(effectivePort)")!
    }

    public var localFrontendBuildID: String {
        let marker = paths.frontendDistDir.appendingPathComponent(".lingo_build_id")
        if let raw = try? String(contentsOf: marker, encoding: .utf8) {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                return trimmed
            }
        }
        return ""
    }

    public var launchBrowserURL: URL {
        let tag = localFrontendBuildID.isEmpty ? "1.3.3" : localFrontendBuildID
        return URL(string: "http://127.0.0.1:\(effectivePort)/?v=\(tag)") ?? localURL
    }

    public var lanURLString: String? {
        let lanEnabled = activeLanAccess || config.lanAccess
        guard lanEnabled, let ip = lanIP, !ip.isEmpty else { return nil }
        return "http://\(ip):\(effectivePort)"
    }

    /// Returns the LAN URL preview for any requested port whenever a local IPv4 address is detected.
    public func lanPreviewURL(port: Int) -> String? {
        guard let ip = lanIP, !ip.isEmpty else { return nil }
        return "http://\(ip):\(DesktopConfig.clampPort(port))"
    }

    public var lanNeedsRestartToApply: Bool {
        isRunning && config.lanAccess && !activeLanAccess
    }

    public func refreshLANIP() {
        lanIP = NetworkUtils.detectLANIPv4()
    }


    public var statusSummary: String {
        if isInstalling { return "正在安装依赖" }
        if isStarting { return "正在启动服务" }
        if isRunning && isHealthy { return "学习机运行中" }
        if isRunning { return "服务启动中" }
        return "已停止"
    }

    // MARK: - Bootstrap & Polling

    public func bootstrap() {
        bootoutLegacyLaunchAgents()
        startTimers()
        Task {
            await refreshEnvironment()
            refreshStats()
            if config.autoStartService && envReport.coreReady && !isRunning {
                appendLog("已开启自动启动，正在拉起本地 Lingo 学习机服务...")
                await startService()
            }
        }
    }

    /// Quietly retires any old v1.1/v1.2 web-console or PyQt launchd agents left running on macOS.
    private func bootoutLegacyLaunchAgents() {
        #if os(macOS)
        let uid = getuid()
        Task.detached(priority: .utility) {
            for label in ["com.lingoreel.studio.console", "com.lingoreel.studio.nativegui"] {
                _ = EnvironmentManager.runQuickCommand(
                    executable: "/bin/launchctl",
                    arguments: ["bootout", "gui/\(uid)/\(label)"],
                    timeoutSec: 3.0
                )
            }
        }
        #endif
    }

    private func startTimers() {
        pollTimer?.invalidate()
        pollTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.tickHealthAndUptime()
            }
        }
    }

    private func tickHealthAndUptime() {
        lanIP = NetworkUtils.detectLANIPv4()
        if isRunning, let start = startedAt {
            let secs = max(0, Int(Date().timeIntervalSince(start)))
            let h = secs / 3600
            let m = (secs % 3600) / 60
            let s = secs % 60
            uptimeText = h > 0
                ? String(format: "%02d:%02d:%02d", h, m, s)
                : String(format: "%02d:%02d", m, s)
            let portToProbe = effectivePort
            Task {
                let ok = await probeHealth(port: portToProbe)
                guard self.isRunning else { return }
                self.isHealthy = ok
                if ok {
                    self.refreshStats()
                }
            }
        } else {
            uptimeText = "00:00"
        }
    }

    public func refreshStats() {
        let store = settingsStore
        Task.detached(priority: .utility) {
            let stats = store.readDatabaseStats()
            await MainActor.run {
                self.dbStats = stats
            }
        }
    }

    public func refreshEnvironment() async {
        isCheckingEnv = true
        let mgr = envManager
        let report = await Task.detached(priority: .userInitiated) {
            mgr.inspectEnvironment()
        }.value
        self.envReport = report
        self.isCheckingEnv = false
    }

    // MARK: - Toast & Logging

    public func showToast(_ message: String, isError: Bool = false) {
        toastMessage = message
        toastIsError = isError
        toastTask?.cancel()
        toastTask = Task {
            try? await Task.sleep(nanoseconds: 3_600_000_000)
            if !Task.isCancelled {
                self.toastMessage = ""
            }
        }
    }

    private func prepareLogFile() {
        let fm = FileManager.default
        if !fm.fileExists(atPath: paths.logFilePath.path) {
            fm.createFile(atPath: paths.logFilePath.path, contents: nil)
        }
        if let fh = try? FileHandle(forWritingTo: paths.logFilePath) {
            fh.seekToEndOfFile()
            logFileHandle = fh
        }
    }

    public func appendLog(_ rawLine: String) {
        let clean = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        let ts = Self.timeFormatter.string(from: Date())
        logs.append(LogEntry(timestamp: ts, line: clean))
        if logs.count > maxLogEntries {
            logs.removeFirst(logs.count - maxLogEntries)
        }
        if let fh = logFileHandle, let data = "[\(ts)] \(clean)\n".data(using: .utf8) {
            try? fh.write(contentsOf: data)
        }
    }

    public func clearLogs() {
        logs.removeAll()
        appendLog("已清空当前日志视图")
    }

    // MARK: - Config & AI Settings

    public func saveDesktopConfig(_ newConfig: DesktopConfig) {
        do {
            var sanitized = newConfig
            sanitized.port = DesktopConfig.clampPort(newConfig.port)
            try configStore.save(sanitized)
            let needsRestart = isRunning && (
                sanitized.port != config.port
                    || sanitized.lanAccess != config.lanAccess
                    || sanitized.accessPassword != config.accessPassword
                    || sanitized.hfMirror != config.hfMirror
            )
            config = sanitized
            if needsRestart {
                showToast("发布配置已保存；请点击「重启服务」以应用新的端口或访问设置。")
            } else {
                showToast("发布配置已保存。")
            }
            appendLog("保存桌面配置：port=\(sanitized.port), lan=\(sanitized.lanAccess), hf_mirror=\(sanitized.hfMirror), auto_start=\(sanitized.autoStartService)")
        } catch {
            showToast("保存配置失败：\(error.localizedDescription)", isError: true)
        }
    }

    /// Saves desktop config and immediately restarts the service if it is currently running
    /// with outdated port/LAN/password/mirror settings.
    public func saveDesktopConfigAndApply(_ newConfig: DesktopConfig) async {
        var sanitized = newConfig
        sanitized.port = DesktopConfig.clampPort(newConfig.port)
        let shouldRestart = isRunning && (
            sanitized.port != effectivePort
                || sanitized.lanAccess != activeLanAccess
                || sanitized.accessPassword != config.accessPassword
                || sanitized.hfMirror != config.hfMirror
        )
        do {
            try configStore.save(sanitized)
            config = sanitized
            refreshLANIP()
            appendLog("保存桌面配置：port=\(sanitized.port), lan=\(sanitized.lanAccess), hf_mirror=\(sanitized.hfMirror), auto_start=\(sanitized.autoStartService)")
        } catch {
            showToast("保存配置失败：\(error.localizedDescription)", isError: true)
            return
        }
        if shouldRestart {
            await restartService()
        } else if !isRunning {
            showToast("发布配置已保存。")
        } else {
            showToast("局域网共享已生效。")
        }
    }


    public func reloadEngineSettings() {
        if let loaded = try? settingsStore.loadPublicSettings() {
            engineSettings = loaded
        }
    }

    public func saveEngineSettings(
        _ draft: EngineSettings,
        clearLLMKey: Bool = false,
        clearASRKey: Bool = false
    ) {
        do {
            let saved = try settingsStore.saveSettings(
                draft,
                clearLLMKey: clearLLMKey,
                clearASRKey: clearASRKey
            )
            engineSettings = saved
            showToast("AI 与语音转写配置已保存（与学习机网页实时共享）。")
            appendLog("已更新共享 AI 模型配置：llm_model=\(saved.llmModel), asr_mode=\(saved.asrMode)")
        } catch {
            showToast("保存 AI 配置失败：\(error.localizedDescription)", isError: true)
        }
    }

    public func testLLMConnection(draft: EngineSettings, allowStoredFallback: Bool = true) async {
        isTestingLLM = true
        llmTestResult = nil
        let effectiveKey = settingsStore.resolveEffectiveLLMKey(
            inputKey: draft.llmAPIKey,
            allowStoredFallback: allowStoredFallback
        )
        let result = await LLMClient.testConnection(
            baseURL: draft.llmBaseURL,
            apiKey: effectiveKey,
            model: draft.llmModel
        )
        llmTestResult = result
        isTestingLLM = false
        appendLog("大模型连通测试：\(result.ok ? "成功" : "失败") — \(result.message)")
        showToast(result.message, isError: !result.ok)
    }

    // MARK: - Dependency Installer

    public func installDependencies() async {
        guard !isInstalling else { return }
        if isRunning {
            await stopService()
        }
        isInstalling = true
        lastErrorBanner = ""
        appendLog("开始执行一键依赖安装与环境修复...")

        let mgr = envManager
        let useMirror = config.hfMirror
        let result = await mgr.installAllDependencies(useMirror: useMirror) { [weak self] line in
            Task { @MainActor [weak self] in
                self?.appendLog(line)
            }
        }

        isInstalling = false
        await refreshEnvironment()
        if result.ok {
            showToast(result.message)
        } else {
            lastErrorBanner = result.message
            showToast(result.message, isError: true)
        }
    }

    // MARK: - Backend Service Lifecycle

    public func startService() async {
        guard !isRunning && !isStarting && !isInstalling else { return }
        lastErrorBanner = ""

        if !envReport.coreReady {
            await refreshEnvironment()
        }
        guard envReport.coreReady else {
            let msg = "核心运行依赖尚未就绪，请先前往「环境与依赖」点击「一键安装 / 修复全部依赖」。"
            lastErrorBanner = msg
            showToast(msg, isError: true)
            return
        }

        let venvPy = envManager.venvPythonURL
        guard FileManager.default.isExecutableFile(atPath: venvPy.path) else {
            let msg = "未找到虚拟环境 Python：\(venvPy.path)"
            lastErrorBanner = msg
            showToast(msg, isError: true)
            return
        }

        let targetPort = config.port
        let targetLan = config.lanAccess

        // Check if a Lingo backend is already healthy on the target port
        if let health = await probeHealthInfo(port: targetPort) {
            let sameBrand = (health["brand"] as? String) == "Lingo"
            let expectedDist = paths.frontendDistDir.resolvingSymlinksInPath().path
            let sameDist = (health["frontend_dist"] as? String) == expectedDist
            let expectedBuild = localFrontendBuildID
            let runningBuild = health["frontend_build"] as? String ?? ""
            let sameBuild = expectedBuild.isEmpty || runningBuild == expectedBuild

            if sameBrand && sameDist && sameBuild {
                appendLog("检测到端口 \(targetPort) 已有最新版 Lingo 服务运行，将直接复用。")
                activePort = targetPort
                activeLanAccess = targetLan
                isRunning = true
                isHealthy = true
                startedAt = Date()
                showToast("Lingo 学习机服务已在端口 \(targetPort) 运行。")
                return
            }

            appendLog("检测到端口 \(targetPort) 运行着旧版后台服务，正在自动关闭并切换至最新 Lingo 版本...")
            await retireStaleLingoBackend(port: targetPort, health: health)
        }

        // Prevent spawning uvicorn on a port occupied by another unrelated program
        if isPortListening(port: targetPort) {
            let msg = "端口 \(targetPort) 已被本机其他程序占用，请在「服务总览」更换端口并保存后再启动。"
            lastErrorBanner = msg
            appendLog("[错误] \(msg)")
            showToast(msg, isError: true)
            return
        }

        isStarting = true
        stoppingIntentionally = false

        try? FileManager.default.createDirectory(at: paths.dataDir, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: paths.whisperCacheDir, withIntermediateDirectories: true)

        let host = targetLan ? "0.0.0.0" : "127.0.0.1"
        let portStr = String(targetPort)
        let proc = Process()
        proc.executableURL = venvPy
        proc.arguments = [
            "-B",
            "-m", "uvicorn",
            "main:app",
            "--host", host,
            "--port", portStr,
            "--no-proxy-headers",
        ]
        proc.currentDirectoryURL = paths.backendDir

        var env = ProcessInfo.processInfo.environment
        let venvBin = paths.venvDir.appendingPathComponent("bin").path
        env["PATH"] = "\(venvBin):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        env["LINGOREEL_DATA_DIR"] = paths.dataDir.path
        env["LINGOREEL_FRONTEND_DIST"] = paths.frontendDistDir.path
        env["LINGOREEL_DESKTOP_APP"] = "1"
        env["HF_HOME"] = paths.whisperCacheDir.path
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        if config.hfMirror {
            env["HF_ENDPOINT"] = LingoReelConstants.hfMirrorURL
        } else {
            env.removeValue(forKey: "HF_ENDPOINT")
        }
        let pw = config.accessPassword.trimmingCharacters(in: .whitespacesAndNewlines)
        if !pw.isEmpty {
            env["APP_ACCESS_PASSWORD"] = pw
        } else {
            env.removeValue(forKey: "APP_ACCESS_PASSWORD")
        }
        proc.environment = env

        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe

        var lineBuf = Data()
        let bufLock = NSLock()
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            if chunk.isEmpty { return }
            bufLock.lock()
            lineBuf.append(chunk)
            var extracted: [String] = []
            while let nl = lineBuf.firstIndex(of: 0x0A) {
                let slice = lineBuf.subdata(in: 0..<nl)
                lineBuf.removeSubrange(0...nl)
                if let text = String(data: slice, encoding: .utf8) {
                    let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !clean.isEmpty { extracted.append(clean) }
                }
            }
            bufLock.unlock()
            if !extracted.isEmpty {
                Task { @MainActor [weak self] in
                    for l in extracted { self?.appendLog(l) }
                }
            }
        }

        proc.terminationHandler = { [weak self] exitedProc in
            pipe.fileHandleForReading.readabilityHandler = nil
            let exitCode = exitedProc.terminationStatus
            Task { @MainActor [weak self] in
                guard let self else { return }
                if self.backendProcess === exitedProc {
                    self.backendProcess = nil
                }
                self.isRunning = false
                self.isHealthy = false
                self.isStarting = false
                self.pid = nil
                self.activePort = nil
                self.activeLanAccess = false
                self.startedAt = nil
                if !self.stoppingIntentionally {
                    let msg = "学习机后台服务意外退出（退出码 \(exitCode)），请前往「运行日志」查看详情。"
                    self.lastErrorBanner = msg
                    self.appendLog("[警告] \(msg)")
                    self.showToast(msg, isError: true)
                } else {
                    self.appendLog("学习机后台服务已安全停止。")
                }
            }
        }

        do {
            try proc.run()
        } catch {
            isStarting = false
            let msg = "无法启动学习机服务：\(error.localizedDescription)"
            lastErrorBanner = msg
            appendLog("[错误] \(msg)")
            showToast(msg, isError: true)
            return
        }

        backendProcess = proc
        pid = proc.processIdentifier
        activePort = targetPort
        activeLanAccess = targetLan
        isRunning = true
        startedAt = Date()
        appendLog("已拉起 Lingo 学习机服务（PID \(proc.processIdentifier)，监听 \(host):\(portStr)）...")

        // Wait up to 20s for /api/health == 200
        var becameHealthy = false
        for _ in 0..<40 {
            if !proc.isRunning { break }
            if await probeHealth(port: targetPort) {
                becameHealthy = true
                break
            }
            try? await Task.sleep(nanoseconds: 500_000_000)
        }

        isStarting = false
        if becameHealthy {
            isHealthy = true
            refreshStats()
            appendLog("Lingo 学习机服务就绪：\(localURL.absoluteString)")
            showToast("Lingo 学习机已就绪，点击「打开学习机」即可使用。")
        } else if proc.isRunning {
            appendLog("服务进程正在初始化（首次启动可能正在生成示例语料），请稍候。")
            showToast("服务启动中（首次可能正在初始化示例语料），请稍候刷新。")
        }
    }

    public func stopService() async {
        stoppingIntentionally = true
        let stopPort = activePort ?? config.port
        guard let proc = backendProcess, proc.isRunning else {
            // If we attached to an already-running local LingoReel service, request graceful shutdown
            if isRunning, let url = URL(string: "http://127.0.0.1:\(stopPort)/api/system/shutdown") {
                var req = URLRequest(url: url, timeoutInterval: 2.5)
                req.httpMethod = "POST"
                req.setValue("http://127.0.0.1:\(stopPort)", forHTTPHeaderField: "Origin")
                _ = try? await URLSession.shared.data(for: req)
            }
            backendProcess = nil
            isRunning = false
            isHealthy = false
            isStarting = false
            pid = nil
            activePort = nil
            activeLanAccess = false
            startedAt = nil
            showToast("学习机服务已停止。")
            return
        }
        appendLog("正在优雅停止学习机服务（PID \(proc.processIdentifier)）...")
        proc.terminate()
        for _ in 0..<25 {
            if !proc.isRunning { break }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        if proc.isRunning {
            kill(proc.processIdentifier, SIGKILL)
        }
        backendProcess = nil
        isRunning = false
        isHealthy = false
        isStarting = false
        pid = nil
        activePort = nil
        activeLanAccess = false
        startedAt = nil
        showToast("学习机服务已停止。")
    }

    public func restartService() async {
        await stopService()
        try? await Task.sleep(nanoseconds: 300_000_000)
        await startService()
    }

    /// Synchronous teardown invoked from `applicationWillTerminate` on the main thread.
    public func shutdownSynchronously() {
        stoppingIntentionally = true
        pollTimer?.invalidate()
        pollTimer = nil
        if let proc = backendProcess, proc.isRunning {
            proc.terminate()
            let deadline = Date().addingTimeInterval(2.5)
            while proc.isRunning && Date() < deadline {
                usleep(50_000)
            }
            if proc.isRunning {
                kill(proc.processIdentifier, SIGKILL)
            }
        }
        backendProcess = nil
        activePort = nil
        activeLanAccess = false
        try? logFileHandle?.close()
        logFileHandle = nil
    }

    private func isPortListening(port: Int) -> Bool {
        #if canImport(Darwin)
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }

        var timeout = timeval(tv_sec: 0, tv_usec: 300_000)
        _ = setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
        _ = setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))

        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = in_port_t(port).bigEndian
        addr.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))

        let res = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        return res == 0
        #else
        return false
        #endif
    }

    private func probeHealthInfo(port: Int) async -> [String: Any]? {
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/health") else { return nil }
        var req = URLRequest(url: url, timeoutInterval: 1.5)
        req.httpMethod = "GET"
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            if let http = resp as? HTTPURLResponse, http.statusCode == 200 {
                if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let svc = obj["service"] as? String,
                   svc == "lingoreel-studio"
                {
                    return obj
                }
            }
        } catch {
            return nil
        }
        return nil
    }

    private func probeHealth(port: Int) async -> Bool {
        await probeHealthInfo(port: port) != nil
    }

    private func retireStaleLingoBackend(port: Int, health: [String: Any]) async {
        if let url = URL(string: "http://127.0.0.1:\(port)/api/system/shutdown") {
            var req = URLRequest(url: url, timeoutInterval: 2.0)
            req.httpMethod = "POST"
            req.setValue("http://127.0.0.1:\(port)", forHTTPHeaderField: "Origin")
            _ = try? await URLSession.shared.data(for: req)
        }
        for _ in 0..<25 {
            if !isPortListening(port: port) {
                return
            }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }

        #if canImport(Darwin)
        var pids: [Int32] = []
        let selfPID = ProcessInfo.processInfo.processIdentifier
        if let hp = health["pid"] as? Int, let pid32 = Int32(exactly: hp), pid32 > 1, pid32 != selfPID {
            pids.append(pid32)
        }
        let lsof = EnvironmentManager.runQuickCommand(
            executable: "/usr/sbin/lsof",
            arguments: ["-t", "-iTCP:\(port)", "-sTCP:LISTEN"],
            timeoutSec: 3.0
        )
        if lsof.0 == 0 {
            for tok in lsof.1.split(whereSeparator: \.isWhitespace) {
                if let p = Int32(tok), p > 1, !pids.contains(p) {
                    let ps = EnvironmentManager.runQuickCommand(
                        executable: "/bin/ps",
                        arguments: ["-p", "\(p)", "-o", "args="],
                        timeoutSec: 2.0
                    )
                    let cmd = ps.1.lowercased()
                    if cmd.contains("uvicorn") && cmd.contains("main:app") {
                        pids.append(p)
                    }
                }
            }
        }
        for p in pids {
            kill(p, SIGTERM)
        }
        for _ in 0..<25 {
            if !isPortListening(port: port) {
                return
            }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        #endif
    }
}
