import Foundation

public final class EnvironmentManager: Sendable {
    public let paths: AppPaths

    public init(paths: AppPaths) {
        self.paths = paths
    }

    public var venvPythonURL: URL {
        paths.venvDir.appendingPathComponent("bin/python")
    }

    /// Runs a quick command synchronously on a background thread and returns (exitCode, stdout+stderr).
    public static func runQuickCommand(
        executable: String,
        arguments: [String],
        environment: [String: String]? = nil,
        timeoutSec: TimeInterval = 12.0
    ) -> (Int32, String) {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: executable)
        proc.arguments = arguments
        if let environment {
            proc.environment = environment
        }
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe

        do {
            try proc.run()
        } catch {
            return (-1, error.localizedDescription)
        }

        let sema = DispatchSemaphore(value: 0)
        proc.terminationHandler = { _ in sema.signal() }
        let waitResult = sema.wait(timeout: .now() + timeoutSec)
        if waitResult == .timedOut {
            proc.terminate()
            return (-2, "timeout")
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        let out = String(data: data, encoding: .utf8) ?? ""
        return (proc.terminationStatus, out.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    /// Parses a Python version string like "3.12.4" and checks 3.10 <= version <= 3.12
    /// (matching desktop_console.py so faster-whisper / PyAV binary wheels remain compatible).
    public static func isSupportedPythonVersion(_ versionString: String) -> Bool {
        let parts = versionString
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .split(separator: ".")
            .compactMap { Int($0) }
        guard parts.count >= 2 else { return false }
        return parts[0] == 3 && (10...12).contains(parts[1])
    }

    /// Discovers a working system or managed Python 3 (3.10 - 3.12) while skipping Apple's non-functional CLT stub.
    public func findSystemPython() -> (path: String, version: String)? {
        let fm = FileManager.default
        let home = fm.homeDirectoryForCurrentUser.path
        var candidates: [String] = [
            "/opt/homebrew/opt/python@3.12/bin/python3.12",
            "/opt/homebrew/bin/python3.12",
            "/opt/homebrew/bin/python3.11",
            "/opt/homebrew/bin/python3.10",
            "/usr/local/opt/python@3.12/bin/python3.12",
            "/usr/local/bin/python3.12",
            "/usr/local/bin/python3.11",
            "/usr/local/bin/python3.10",
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
            "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
            "\(home)/.pyenv/shims/python3",
            "\(home)/miniconda3/bin/python3",
            "\(home)/anaconda3/bin/python3",
            "\(home)/miniforge3/bin/python3",
            "/usr/bin/python3",
        ]

        // Also scan uv-managed standalone Python installations under Application Support/LingoReelStudio/python/
        let managedPyRoot = paths.appSupportDir.appendingPathComponent("python", isDirectory: true)
        if let entries = try? fm.contentsOfDirectory(at: managedPyRoot, includingPropertiesForKeys: nil) {
            for entry in entries.sorted(by: { $0.lastPathComponent > $1.lastPathComponent }) {
                for name in ["bin/python3.12", "bin/python3.11", "bin/python3.10", "bin/python3"] {
                    let p = entry.appendingPathComponent(name).path
                    if fm.isExecutableFile(atPath: p) {
                        candidates.insert(p, at: 0)
                    }
                }
            }
        }

        // Include PATH entries if present
        if let pathEnv = ProcessInfo.processInfo.environment["PATH"] {
            for dir in pathEnv.split(separator: ":") {
                let p = "\(dir)/python3"
                if !candidates.contains(p) {
                    candidates.append(p)
                }
            }
        }

        let probeCode = "import sys, venv; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
        var env = ProcessInfo.processInfo.environment
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        for cand in candidates {
            guard fm.isExecutableFile(atPath: cand) else { continue }
            // Avoid triggering macOS GUI "Install Xcode CLT" popup if /usr/bin/python3 is an empty stub
            if cand == "/usr/bin/python3" {
                let cltCheck = Self.runQuickCommand(
                    executable: "/usr/bin/xcode-select",
                    arguments: ["-p"],
                    timeoutSec: 3.0
                )
                if cltCheck.0 != 0 {
                    continue
                }
            }
            let (code, out) = Self.runQuickCommand(
                executable: cand,
                arguments: ["-B", "-c", probeCode],
                environment: env,
                timeoutSec: 5.0
            )
            if code == 0, let firstLine = out.split(separator: "\n").first.map(String.init),
               Self.isSupportedPythonVersion(firstLine)
            {
                return (cand, firstLine)
            }
        }
        return nil
    }

    public func findSystemFFmpeg() -> String? {
        let fm = FileManager.default
        let venvFFmpeg = paths.venvDir.appendingPathComponent("bin/ffmpeg").path
        let candidates = [
            venvFFmpeg,
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/usr/bin/ffmpeg",
        ]
        for c in candidates where fm.isExecutableFile(atPath: c) {
            return c
        }
        return nil
    }

    /// Probes all runtime dependencies on a background thread and returns a full report.
    public func inspectEnvironment() -> EnvironmentReport {
        let fm = FileManager.default
        let sysPy = findSystemPython()
        let venvPyPath = venvPythonURL.path
        let venvExists = fm.isExecutableFile(atPath: venvPyPath)

        var venvPythonVersion = ""
        var pkgStatus: [String: Bool] = [:]
        var imageioFFmpegPath = ""

        if venvExists {
            let probeScript = """
            import importlib.util, json, sys
            mods = ["fastapi", "uvicorn", "multipart", "httpx", "eng_to_ipa", "numpy", "faster_whisper", "edge_tts", "imageio_ffmpeg"]
            res = {m: (importlib.util.find_spec(m) is not None) for m in mods}
            ff = ""
            if res.get("imageio_ffmpeg"):
                try:
                    import imageio_ffmpeg
                    ff = imageio_ffmpeg.get_ffmpeg_exe() or ""
                except Exception:
                    ff = ""
            print(json.dumps({
                "py": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "mods": res,
                "imageio_ffmpeg": ff
            }))
            """
            let (code, out) = Self.runQuickCommand(
                executable: venvPyPath,
                arguments: ["-B", "-c", probeScript],
                timeoutSec: 12.0
            )
            if code == 0, let jsonData = out.data(using: .utf8),
               let obj = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any]
            {
                venvPythonVersion = obj["py"] as? String ?? ""
                if let mods = obj["mods"] as? [String: Bool] {
                    pkgStatus = mods
                }
                imageioFFmpegPath = obj["imageio_ffmpeg"] as? String ?? ""
            }
        }

        let sysFFmpeg = findSystemFFmpeg()
        let effectiveFFmpeg: String? = sysFFmpeg ?? (imageioFFmpegPath.isEmpty ? nil : imageioFFmpegPath)

        let coreWebOK = (pkgStatus["fastapi"] == true)
            && (pkgStatus["uvicorn"] == true)
            && (pkgStatus["multipart"] == true)
            && (pkgStatus["httpx"] == true)
            && (pkgStatus["numpy"] == true)
            && (pkgStatus["eng_to_ipa"] == true)
        let whisperOK = pkgStatus["faster_whisper"] == true
        let ttsOK = pkgStatus["edge_tts"] == true

        let items: [DependencyItem] = [
            DependencyItem(
                id: "python3",
                title: "Python 3 运行时（3.10 - 3.12）",
                detail: sysPy != nil ? "已检测到兼容的系统 Python 3 环境" : "未检测到 Python 3.10 - 3.12，请先通过 Homebrew 或 python.org 安装",
                required: true,
                installed: sysPy != nil || venvExists,
                version: sysPy?.version ?? venvPythonVersion,
                path: sysPy?.path ?? (venvExists ? venvPyPath : "")
            ),
            DependencyItem(
                id: "venv",
                title: "独立应用虚拟环境（.venv）",
                detail: venvExists ? "独立隔离环境已就绪，不污染系统 Python" : "尚未创建应用隔离环境，点击一键安装将自动创建",
                required: true,
                installed: venvExists,
                version: venvPythonVersion,
                path: paths.venvDir.path
            ),
            DependencyItem(
                id: "core_web",
                title: "核心服务与音标引擎（FastAPI / Uvicorn / NumPy）",
                detail: coreWebOK ? "Web 学习机后端与音频分析依赖完整" : "缺少核心后端依赖，点击一键安装即可补全",
                required: true,
                installed: coreWebOK,
                version: coreWebOK ? "已就绪" : "待安装",
                path: ""
            ),
            DependencyItem(
                id: "ffmpeg",
                title: "音视频编解码引擎（FFmpeg）",
                detail: effectiveFFmpeg != nil ? "支持视频拆解、连续跟读自动切片与录音评测" : "未检测到系统或内置 FFmpeg，点击一键安装将自动补装",
                required: true,
                installed: effectiveFFmpeg != nil,
                version: effectiveFFmpeg != nil ? "已就绪" : "待安装",
                path: effectiveFFmpeg ?? ""
            ),
            DependencyItem(
                id: "whisper",
                title: "离线语音识别与配音引擎（Faster-Whisper / Edge-TTS）",
                detail: whisperOK
                    ? (ttsOK ? "离线语音转写、跟读精准打分与示例配音全部就绪" : "离线语音转写与跟读打分已就绪")
                    : "安装后即可无 Key 离线精准跟读打分与自动字幕转写",
                required: false,
                installed: whisperOK,
                version: whisperOK ? "已就绪" : "推荐安装",
                path: ""
            ),
        ]

        let coreReady = items.filter(\.required).allSatisfy(\.installed)
        let allReady = items.allSatisfy(\.installed)

        return EnvironmentReport(
            pythonPath: sysPy?.path ?? (venvExists ? venvPyPath : nil),
            pythonVersion: sysPy?.version ?? venvPythonVersion,
            venvReady: venvExists,
            ffmpegPath: effectiveFFmpeg,
            items: items,
            coreReady: coreReady,
            allReady: allReady,
            checkedAt: Date()
        )
    }

    /// Streams output from a subprocess asynchronously on a background queue.
    public static func runStreamingCommand(
        executable: String,
        arguments: [String],
        currentDirectory: URL? = nil,
        environment: [String: String]? = nil,
        onLine: @escaping @Sendable (String) -> Void
    ) async -> Int32 {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let proc = Process()
                proc.executableURL = URL(fileURLWithPath: executable)
                proc.arguments = arguments
                if let currentDirectory {
                    proc.currentDirectoryURL = currentDirectory
                }
                if let environment {
                    proc.environment = environment
                }
                let pipe = Pipe()
                proc.standardOutput = pipe
                proc.standardError = pipe

                var buffer = Data()
                let lock = NSLock()
                pipe.fileHandleForReading.readabilityHandler = { handle in
                    let chunk = handle.availableData
                    if chunk.isEmpty { return }
                    lock.lock()
                    buffer.append(chunk)
                    while let nl = buffer.firstIndex(of: 0x0A) {
                        let lineData = buffer.subdata(in: 0..<nl)
                        buffer.removeSubrange(0...nl)
                        if let text = String(data: lineData, encoding: .utf8) {
                            let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
                            if !clean.isEmpty {
                                onLine(clean)
                            }
                        }
                    }
                    lock.unlock()
                }

                do {
                    try proc.run()
                    proc.waitUntilExit()
                } catch {
                    onLine("[错误] 启动安装命令失败：\(error.localizedDescription)")
                    pipe.fileHandleForReading.readabilityHandler = nil
                    continuation.resume(returning: -1)
                    return
                }

                pipe.fileHandleForReading.readabilityHandler = nil
                let remaining = pipe.fileHandleForReading.readDataToEndOfFile()
                lock.lock()
                buffer.append(remaining)
                if !buffer.isEmpty, let tail = String(data: buffer, encoding: .utf8) {
                    for rawLine in tail.split(separator: "\n") {
                        let clean = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
                        if !clean.isEmpty { onLine(clean) }
                    }
                }
                lock.unlock()
                continuation.resume(returning: proc.terminationStatus)
            }
        }
    }

    private func ensureUVBinary(
        env: [String: String],
        onLine: @escaping @Sendable (String) -> Void
    ) async -> String? {
        let fm = FileManager.default
        let binDir = paths.appSupportDir.appendingPathComponent("bin", isDirectory: true)
        try? fm.createDirectory(at: binDir, withIntermediateDirectories: true)
        let localUV = binDir.appendingPathComponent("uv").path

        for cand in [localUV, "/opt/homebrew/bin/uv", "/usr/local/bin/uv"] {
            if fm.isExecutableFile(atPath: cand) {
                return cand
            }
        }

        onLine("未检测到本机兼容 Python 3.10-3.12，正在自动下载轻量安装工具 uv（用于免配置安装 Python 3.12）...")
        let archOut = Self.runQuickCommand(executable: "/usr/bin/uname", arguments: ["-m"], timeoutSec: 3.0).1
        let uvURL = archOut == "arm64"
            ? "https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz"
            : "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-apple-darwin.tar.gz"

        let script = """
        set -e
        TMP_DIR="$(mktemp -d)"
        trap 'rm -rf "$TMP_DIR"' EXIT
        curl -fsSL --connect-timeout 15 --max-time 90 "$1" -o "$TMP_DIR/uv.tar.gz"
        tar -xzf "$TMP_DIR/uv.tar.gz" -C "$TMP_DIR"
        UV_FOUND="$(find "$TMP_DIR" -maxdepth 2 -name uv -type f | head -n 1)"
        cp "$UV_FOUND" "$2"
        chmod +x "$2"
        """
        let rc = await Self.runStreamingCommand(
            executable: "/bin/bash",
            arguments: ["-c", script, "--", uvURL, localUV],
            environment: env,
            onLine: onLine
        )
        if rc == 0 && fm.isExecutableFile(atPath: localUV) {
            return localUV
        }
        return nil
    }

    /// Creates `.venv` if missing (auto-downloading standalone Python 3.12 via uv if needed),
    /// installs `requirements.txt` (Tsinghua mirror -> PyPI fallback),
    /// and symlinks `imageio-ffmpeg` into `.venv/bin/ffmpeg`.
    public func installAllDependencies(
        useMirror: Bool,
        onLine: @escaping @Sendable (String) -> Void
    ) async -> (ok: Bool, message: String) {
        let fm = FileManager.default
        let pyDir = paths.appSupportDir.appendingPathComponent("python", isDirectory: true)
        let uvCache = paths.appSupportDir.appendingPathComponent("uv-cache", isDirectory: true)
        try? fm.createDirectory(at: paths.dataDir, withIntermediateDirectories: true)
        try? fm.createDirectory(at: paths.venvDir.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? fm.createDirectory(at: pyDir, withIntermediateDirectories: true)
        try? fm.createDirectory(at: uvCache, withIntermediateDirectories: true)

        var baseEnv = ProcessInfo.processInfo.environment
        baseEnv["PYTHONDONTWRITEBYTECODE"] = "1"
        baseEnv["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        baseEnv["PYTHONUNBUFFERED"] = "1"
        baseEnv["UV_PYTHON_INSTALL_DIR"] = pyDir.path
        baseEnv["UV_CACHE_DIR"] = uvCache.path
        baseEnv["PATH"] = "\(paths.venvDir.appendingPathComponent("bin").path):\(paths.appSupportDir.appendingPathComponent("bin").path):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

        var uvPath: String? = nil

        // Step 1: Ensure .venv exists (auto-install Python 3.12 via uv if none found locally)
        if !fm.isExecutableFile(atPath: venvPythonURL.path) {
            var chosenPython = findSystemPython()
            if chosenPython == nil {
                uvPath = await ensureUVBinary(env: baseEnv, onLine: onLine)
                if let uv = uvPath {
                    onLine("[1/3] 正在通过 uv 自动安装独立版 Python 3.12...")
                    let pyRC = await Self.runStreamingCommand(
                        executable: uv,
                        arguments: ["python", "install", "3.12"],
                        environment: baseEnv,
                        onLine: onLine
                    )
                    if pyRC == 0 {
                        let findRes = Self.runQuickCommand(
                            executable: uv,
                            arguments: ["python", "find", "3.12"],
                            environment: baseEnv,
                            timeoutSec: 10.0
                        )
                        if findRes.0 == 0, !findRes.1.isEmpty, fm.isExecutableFile(atPath: findRes.1) {
                            chosenPython = (findRes.1, "3.12")
                        } else {
                            chosenPython = findSystemPython()
                        }
                    }
                }
            }

            guard let sysPy = chosenPython else {
                onLine("[错误] 未能自动获取 Python 3.10 - 3.12（请检查网络，或前往 python.org 手动安装 Python 3.12）。")
                return (false, "未能获取 Python 3.12，请检查网络连接或点击「下载 Python 3」手动安装后重试。")
            }
            onLine("[1/3] 正在使用 \(sysPy.path) (Python \(sysPy.version)) 创建独立虚拟环境...")
            let rc: Int32
            if let uv = uvPath {
                rc = await Self.runStreamingCommand(
                    executable: uv,
                    arguments: ["venv", "--seed", "--python", sysPy.path, paths.venvDir.path],
                    environment: baseEnv,
                    onLine: onLine
                )
            } else {
                rc = await Self.runStreamingCommand(
                    executable: sysPy.path,
                    arguments: ["-B", "-m", "venv", paths.venvDir.path],
                    environment: baseEnv,
                    onLine: onLine
                )
            }
            if rc != 0 || !fm.isExecutableFile(atPath: venvPythonURL.path) {
                return (false, "创建 Python 虚拟环境失败（退出码 \(rc)），请查看运行日志。")
            }
        } else {
            onLine("[1/3] 已检测到现有虚拟环境：\(paths.venvDir.path)")
        }

        // Step 2: Install requirements.txt (excluding PyQt6 / pywebview since native SwiftUI replaces them)
        let reqFile = paths.backendDir.appendingPathComponent("requirements.txt")
        guard fm.fileExists(atPath: reqFile.path) else {
            return (false, "未找到依赖清单：\(reqFile.path)")
        }

        let filteredReqURL = paths.dataDir.appendingPathComponent(".requirements_native.txt")
        if let rawReq = try? String(contentsOf: reqFile, encoding: .utf8) {
            let lines = rawReq
                .split(separator: "\n", omittingEmptySubsequences: false)
                .filter { line in
                    let lower = line.lowercased()
                    return !lower.contains("pyqt6") && !lower.contains("pywebview")
                }
            try? lines.joined(separator: "\n").write(to: filteredReqURL, atomically: true, encoding: .utf8)
        }
        let effectiveReqPath = fm.fileExists(atPath: filteredReqURL.path) ? filteredReqURL.path : reqFile.path

        if uvPath == nil {
            let existingUVCandidates = [
                paths.appSupportDir.appendingPathComponent("bin/uv").path,
                "/opt/homebrew/bin/uv",
                "/usr/local/bin/uv",
            ]
            for cand in existingUVCandidates where fm.isExecutableFile(atPath: cand) {
                uvPath = cand
                break
            }
        }
        if uvPath == nil {
            let pipProbe = Self.runQuickCommand(
                executable: venvPythonURL.path,
                arguments: ["-B", "-m", "pip", "--version"],
                environment: baseEnv,
                timeoutSec: 8.0
            )
            if pipProbe.0 != 0 {
                onLine("当前虚拟环境未内置 pip，正在自动准备 uv 完成高速依赖安装...")
                uvPath = await ensureUVBinary(env: baseEnv, onLine: onLine)
            }
        }

        onLine("[2/3] 正在安装 Lingo 后端引擎、FFmpeg 与本地 Whisper 依赖...")
        var pipRC: Int32 = -1
        if let uv = uvPath {
            var uvArgs = ["pip", "install", "--python", venvPythonURL.path, "-r", effectiveReqPath]
            if useMirror {
                uvArgs.append(contentsOf: ["--default-index", LingoReelConstants.tsinghuaPyPIURL])
                onLine("使用国内清华 PyPI 镜像加速下载...")
            }
            pipRC = await Self.runStreamingCommand(
                executable: uv,
                arguments: uvArgs,
                environment: baseEnv,
                onLine: onLine
            )
            if pipRC != 0 && useMirror {
                onLine("清华镜像安装未完全成功，正在自动切换官方 PyPI 重试...")
                pipRC = await Self.runStreamingCommand(
                    executable: uv,
                    arguments: ["pip", "install", "--python", venvPythonURL.path, "-r", effectiveReqPath],
                    environment: baseEnv,
                    onLine: onLine
                )
            }
        } else {
            var pipArgs = ["-B", "-m", "pip", "install", "--upgrade", "-r", effectiveReqPath]
            if useMirror {
                pipArgs.append(contentsOf: ["-i", LingoReelConstants.tsinghuaPyPIURL, "--trusted-host", "pypi.tuna.tsinghua.edu.cn"])
                onLine("使用国内清华 PyPI 镜像加速下载...")
            }
            pipRC = await Self.runStreamingCommand(
                executable: venvPythonURL.path,
                arguments: pipArgs,
                environment: baseEnv,
                onLine: onLine
            )
            if pipRC != 0 && useMirror {
                onLine("清华镜像安装未完全成功，正在自动切换官方 PyPI 重试...")
                pipRC = await Self.runStreamingCommand(
                    executable: venvPythonURL.path,
                    arguments: ["-B", "-m", "pip", "install", "--upgrade", "-r", effectiveReqPath],
                    environment: baseEnv,
                    onLine: onLine
                )
            }
        }
        if pipRC != 0 {
            return (false, "依赖安装失败（退出码 \(pipRC)），请检查网络连接并查看运行日志。")
        }

        // Step 3: Symlink imageio-ffmpeg binary into .venv/bin/ffmpeg if system ffmpeg isn't in venv
        onLine("[3/3] 正在配置内置 FFmpeg 快捷入口...")
        let linkScript = """
        import os, pathlib, sys
        try:
            import imageio_ffmpeg
            src = imageio_ffmpeg.get_ffmpeg_exe()
            dst = pathlib.Path(sys.argv[1])
            if src and os.path.exists(src) and not dst.exists():
                os.symlink(src, dst)
                print(f'已链接内置 FFmpeg: {src}')
            else:
                print('FFmpeg 入口已就绪')
        except Exception as exc:
            print(f'跳过内置 FFmpeg 软链: {exc}')
        """
        let ffmpegDst = paths.venvDir.appendingPathComponent("bin/ffmpeg").path
        _ = await Self.runStreamingCommand(
            executable: venvPythonURL.path,
            arguments: ["-B", "-c", linkScript, ffmpegDst],
            environment: baseEnv,
            onLine: onLine
        )

        onLine("[完成] Lingo 全部运行环境与核心依赖安装成功！")
        return (true, "依赖安装与环境修复完成，现可一键启动 Lingo 学习机服务。")
    }
}
