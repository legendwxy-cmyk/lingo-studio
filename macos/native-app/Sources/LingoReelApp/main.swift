import AppKit
import Foundation
import LingoReelCore

/// Runs headless end-to-end verification on real macOS CI runners without needing a GUI session.
func runSelfTest() -> Bool {
    let fm = FileManager.default
    let tmpRoot = fm.temporaryDirectory.appendingPathComponent("lingo_native_selftest_\(UUID().uuidString)", isDirectory: true)
    defer { try? fm.removeItem(at: tmpRoot) }

    do {
        try fm.createDirectory(at: tmpRoot, withIntermediateDirectories: true)

        // 1. Config persistence, partial JSON resilience & port validation
        let cfgURL = tmpRoot.appendingPathComponent("desktop_config.json")
        let cfgStore = ConfigStore(configURL: cfgURL)
        try "{\"port\": 8123, \"lan_access\": true}".write(to: cfgURL, atomically: true, encoding: .utf8)
        let partialCfg = cfgStore.load()
        guard partialCfg.port == 8123 && partialCfg.lanAccess && partialCfg.hfMirror && !partialCfg.autoStartService else {
            fputs("SELF_TEST_FAIL: partial legacy config decode failed\n", stderr)
            return false
        }
        let savedCfg = DesktopConfig(port: 8123, lanAccess: true, accessPassword: "demo", hfMirror: true, autoStartService: false)
        try cfgStore.save(savedCfg)
        let loadedCfg = cfgStore.load()
        guard loadedCfg == savedCfg else {
            fputs("SELF_TEST_FAIL: config roundtrip mismatch\n", stderr)
            return false
        }

        // 2. Native SQLite settings store + secret masking + masked preservation + clear fallback guard
        let settingsStore = SettingsStore(dbURL: tmpRoot.appendingPathComponent("lexifilm.db"))
        var s = try settingsStore.loadPublicSettings()
        s.llmBaseURL = "https://api.deepseek.com/v1"
        s.llmModel = "deepseek-chat"
        s.llmAPIKey = "sk-test1234567890abcd"
        let pub = try settingsStore.saveSettings(s)
        guard pub.hasLLMKey, SecretMasker.isMasked(pub.llmAPIKey), pub.llmAPIKey == "sk-••••abcd" else {
            fputs("SELF_TEST_FAIL: secret masking mismatch: \(pub.llmAPIKey)\n", stderr)
            return false
        }
        guard settingsStore.resolveEffectiveLLMKey(inputKey: "", allowStoredFallback: false).isEmpty else {
            fputs("SELF_TEST_FAIL: allowStoredFallback=false still returned stored key\n", stderr)
            return false
        }
        var s2 = pub
        s2.llmModel = "deepseek-reasoner"
        _ = try settingsStore.saveSettings(s2)
        let rawAfter = try settingsStore.readRawDictionary()
        guard rawAfter["llm_api_key"] == "sk-test1234567890abcd", rawAfter["llm_model"] == "deepseek-reasoner" else {
            fputs("SELF_TEST_FAIL: masked key preservation failed\n", stderr)
            return false
        }

        // 3. Preset ASR preservation & URL suffix guards
        var presetTest = EngineSettings(from: [:])
        presetTest.asrBaseURL = "https://custom-asr.example.com/v1"
        if let deepseek = ProviderPreset.all.first(where: { $0.id == "deepseek" }) {
            deepseek.apply(to: &presetTest)
        }
        guard presetTest.asrBaseURL == "https://custom-asr.example.com/v1" else {
            fputs("SELF_TEST_FAIL: DeepSeek preset overwrote asrBaseURL\n", stderr)
            return false
        }
        guard EndpointURLBuilder.chatCompletionsURL(from: "https://api.deepseek.com/v1/chat/completions") == "https://api.deepseek.com/v1/chat/completions",
              EndpointURLBuilder.audioTranscriptionsURL(from: "https://api.openai.com/v1/audio/transcriptions") == "https://api.openai.com/v1/audio/transcriptions"
        else {
            fputs("SELF_TEST_FAIL: endpoint URL guard failed\n", stderr)
            return false
        }

        // 4. Environment probe runs cleanly without crashing on real macOS
        let resolvedPaths = AppPaths.resolveDefault()
        let envMgr = EnvironmentManager(paths: resolvedPaths)
        let report = envMgr.inspectEnvironment()
        guard report.items.count == 5 else {
            fputs("SELF_TEST_FAIL: expected 5 dependency items, got \(report.items.count)\n", stderr)
            return false
        }

        // 5. Verify bundled backend, frontend & transparent 3D Lingo wordmark when launched from Lingo.app
        if CommandLine.arguments.contains("--verify-bundle") {
            let mainPy = resolvedPaths.backendDir.appendingPathComponent("main.py").path
            let indexHtml = resolvedPaths.frontendDistDir.appendingPathComponent("index.html").path
            guard fm.fileExists(atPath: mainPy), fm.fileExists(atPath: indexHtml) else {
                fputs("SELF_TEST_FAIL: missing bundled resources mainPy=\(mainPy) indexHtml=\(indexHtml)\n", stderr)
                return false
            }
            guard LingoBrandAssets.wordmarkNSImage != nil else {
                fputs("SELF_TEST_FAIL: missing bundled transparent 3D lingo-logo.png\n", stderr)
                return false
            }
        }

        print("LINGO_NATIVE_MACOS_SWIFTUI_SELF_TEST_OK (python=\(report.pythonVersion.isEmpty ? "none" : report.pythonVersion), items=\(report.items.count))")
        return true
    } catch {
        fputs("SELF_TEST_FAIL: \(error.localizedDescription)\n", stderr)
        return false
    }
}

if CommandLine.arguments.contains("--self-test") {
    exit(runSelfTest() ? 0 : 1)
}

// Single-instance check: wake & show matching Lingo version; cleanly retire any older cached bundle version on upgrade
let currentPID = ProcessInfo.processInfo.processIdentifier
let activeBundleID = Bundle.main.bundleIdentifier ?? LingoReelConstants.bundleIdentifier
let myBundleURL = Bundle.main.bundleURL.standardizedFileURL
let others = NSRunningApplication.runningApplications(withBundleIdentifier: activeBundleID)
    .filter { $0.processIdentifier != currentPID }
if !others.isEmpty {
    if let sameVersion = others.first(where: { $0.bundleURL?.standardizedFileURL == myBundleURL }) {
        DistributedNotificationCenter.default().postNotificationName(
            lingoShowWindowNotification,
            object: nil,
            userInfo: nil,
            deliverImmediately: true
        )
        sameVersion.activate(options: [.activateIgnoringOtherApps, .activateAllWindows])
        exit(0)
    }
    for stale in others {
        stale.terminate()
    }
    let deadline = Date().addingTimeInterval(2.5)
    while Date() < deadline && others.contains(where: { !$0.isTerminated }) {
        usleep(50_000)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
