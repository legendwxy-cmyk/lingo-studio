import AppKit
import LingoReelCore
import SwiftUI

struct OverviewTab: View {
    @ObservedObject var manager: ServiceManager
    let skin: LingoSkin
    let onOpenWebApp: () -> Void
    let onGoEnvironment: () -> Void

    @State private var portText: String = "8000"
    @State private var lanAccess: Bool = false
    @State private var accessPassword: String = ""
    @State private var hfMirror: Bool = true
    @State private var autoStartService: Bool = false
    @State private var initialized: Bool = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                headerSection

                if !manager.envReport.items.isEmpty && !manager.envReport.coreReady {
                    missingDepsBanner
                }

                serviceHeroDeck
                statsRow
                publishConfigCard
            }
            .padding(24)
        }
        .onAppear {
            if !initialized {
                syncFromManager()
                initialized = true
            }
            manager.refreshLANIP()
            manager.refreshStats()
        }
        .onChange(of: manager.config) { _ in
            syncFromManager()
        }
        .onChange(of: lanAccess) { isOn in
            if isOn {
                manager.refreshLANIP()
            }
        }
    }

    private var draftPort: Int {
        let parsed = Int(portText.trimmingCharacters(in: .whitespacesAndNewlines))
            ?? LingoReelConstants.defaultPort
        return DesktopConfig.clampPort(parsed)
    }

    private var draftDesktopConfig: DesktopConfig {
        DesktopConfig(
            port: draftPort,
            lanAccess: lanAccess,
            accessPassword: accessPassword,
            hfMirror: hfMirror,
            autoStartService: autoStartService
        )
    }

    private var displayedLanURL: String? {
        guard lanAccess || manager.activeLanAccess else { return nil }
        let targetPort = lanAccess ? draftPort : manager.effectivePort
        return manager.lanPreviewURL(port: targetPort)
    }

    private var isLanLiveAndActive: Bool {
        manager.isRunning && manager.activeLanAccess && manager.effectivePort == draftPort
    }

    private func syncFromManager() {
        portText = String(manager.config.port)
        lanAccess = manager.config.lanAccess
        accessPassword = manager.config.accessPassword
        hfMirror = manager.config.hfMirror
        autoStartService = manager.config.autoStartService
    }

    private var headerSection: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 4) {
                Text("服务总览与主机发布")
                    .font(.system(size: 22, weight: .black, design: .rounded))
                    .foregroundColor(skin.ink)
                Text("一键启停本机 Lingo 学习机服务、设置监听端口与局域网共享，随后即可在浏览器进入学习机。")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundColor(skin.inkMuted)
            }
            Spacer()
            if let pid = manager.pid, manager.isRunning {
                LingoPill(skin: skin, text: "PID \(pid)", tone: .dark, mono: true)
            }
        }
    }

    private var missingDepsBanner: some View {
        LingoCard(skin: skin, highlight: true, padding: 16) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(skin.ink)
                        .frame(width: 44, height: 44)
                    Image(systemName: "wrench.and.screwdriver.fill")
                        .font(.system(size: 19, weight: .bold))
                        .foregroundColor(skin.accent)
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text("首次运行检测到缺失运行依赖")
                        .font(.system(size: 14.5, weight: .black, design: .rounded))
                        .foregroundColor(skin.ink)
                    Text("前往「环境与依赖」点击一键安装，全自动配置 Python 3.12 隔离环境、FFmpeg 与本地 Whisper。")
                        .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                        .foregroundColor(skin.inkSub)
                }

                Spacer()

                Button("前往一键安装") {
                    onGoEnvironment()
                }
                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .darkAccent))
            }
        }
    }

    // MARK: - Playful 3D Tactile Hero Deck (Mirrors Web 3D Speed Dial + Big Hardware Keys)

    private var serviceHeroDeck: some View {
        LingoCard(skin: skin, highlight: manager.isRunning && manager.isHealthy, padding: 20) {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .center, spacing: 20) {
                    statusDialView

                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 8) {
                            Text(manager.statusSummary)
                                .font(.system(size: 20, weight: .black, design: .rounded))
                                .foregroundColor(skin.ink)

                            LingoPill(
                                skin: skin,
                                text: manager.isRunning ? "在线 :\(manager.effectivePort)" : "待机中",
                                tone: manager.isRunning ? .mint : .keycap,
                                mono: true
                            )
                        }

                        HStack(spacing: 10) {
                            HStack(spacing: 6) {
                                Image(systemName: "link")
                                    .font(.system(size: 11.5, weight: .bold))
                                Text(manager.localURL.absoluteString)
                                    .font(.system(size: 12.5, weight: .bold, design: .monospaced))
                                    .textSelection(.enabled)
                            }
                            .foregroundColor(skin.ink)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .fill(Color.white.opacity(manager.isRunning && manager.isHealthy ? 0.72 : 0.95))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                                            .strokeBorder(skin.ink.opacity(0.12), lineWidth: 1)
                                    )
                            )

                            if manager.isRunning {
                                LingoPill(skin: skin, text: "已运行 \(manager.uptimeText)", tone: .dark, mono: true)
                            }
                        }

                        // Chunky 3D Hardware Control Buttons
                        HStack(spacing: 10) {
                            if !manager.isRunning {
                                Button {
                                    let cfgToStart = draftDesktopConfig
                                    portText = String(cfgToStart.port)
                                    Task {
                                        if cfgToStart != manager.config {
                                            manager.saveDesktopConfig(cfgToStart)
                                        }
                                        await manager.startService()
                                    }
                                } label: {
                                    HStack(spacing: 7) {
                                        Image(systemName: "play.fill")
                                        Text(manager.isStarting ? "正在启动..." : "启动 Lingo 学习机")
                                    }
                                }
                                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .darkAccent))
                                .disabled(manager.isStarting || manager.isInstalling || !manager.envReport.coreReady)
                            } else {
                                Button(action: onOpenWebApp) {
                                    HStack(spacing: 7) {
                                        Image(systemName: "safari.fill")
                                        Text("在浏览器打开学习机")
                                    }
                                }
                                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .darkAccent))

                                Button {
                                    Task { await manager.restartService() }
                                } label: {
                                    HStack(spacing: 6) {
                                        Image(systemName: "arrow.clockwise")
                                        Text("重启服务")
                                    }
                                }
                                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white))
                                .disabled(manager.isStarting || manager.isInstalling)

                                Button {
                                    Task { await manager.stopService() }
                                } label: {
                                    HStack(spacing: 6) {
                                        Image(systemName: "stop.fill")
                                        Text("停止服务")
                                    }
                                }
                                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .coral))
                                .disabled(manager.isInstalling)
                            }

                            Button {
                                copyToPasteboard(manager.localURL.absoluteString)
                                manager.showToast("已复制本机访问地址")
                            } label: {
                                HStack(spacing: 5) {
                                    Image(systemName: "doc.on.doc")
                                    Text("复制网址")
                                }
                            }
                            .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white))
                        }
                    }
                    Spacer()
                }

                if lanAccess || manager.activeLanAccess {
                    HStack(spacing: 10) {
                        Image(systemName: "wifi")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(skin.sky)
                        if let lanURL = displayedLanURL {
                            Text("局域网同 Wi-Fi 访问：")
                                .font(.system(size: 12.5, weight: .bold, design: .rounded))
                                .foregroundColor(skin.ink)
                            Text(lanURL)
                                .font(.system(size: 12.5, weight: .bold, design: .monospaced))
                                .foregroundColor(skin.sky)
                                .textSelection(.enabled)
                            if isLanLiveAndActive {
                                LingoPill(skin: skin, text: "已生效", tone: .mint)
                            } else if manager.isRunning {
                                LingoPill(skin: skin, text: "待重启生效", tone: .keycap)
                            } else {
                                LingoPill(skin: skin, text: "启动后生效", tone: .keycap)
                            }
                            Spacer()
                            if manager.isRunning && !isLanLiveAndActive {
                                Button("立即应用并重启") {
                                    let updated = draftDesktopConfig
                                    portText = String(updated.port)
                                    Task { await manager.saveDesktopConfigAndApply(updated) }
                                }
                                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .darkAccent, compact: true))
                                .disabled(manager.isStarting || manager.isInstalling)
                            }
                            Button("复制局域网地址") {
                                copyToPasteboard(lanURL)
                                manager.showToast("已复制局域网地址：\(lanURL)")
                            }
                            .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white, compact: true))
                        } else {
                            Text("局域网共享已开启，但暂未检测到本机 Wi-Fi / 局域网 IP")
                                .font(.system(size: 12.5, weight: .bold, design: .rounded))
                                .foregroundColor(skin.inkSub)
                            Spacer()
                            Button("重新检测 IP") {
                                manager.refreshLANIP()
                            }
                            .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white, compact: true))
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 9)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(Color.white.opacity(0.86))
                    )
                }
            }
        }
    }

    private var statusDialView: some View {
        ZStack {
            // Outer 3D Hardware Dial Ring
            Circle()
                .fill(
                    RadialGradient(
                        colors: skin.dialOuterColors,
                        center: UnitPoint(x: 0.30, y: 0.24),
                        startRadius: 4,
                        endRadius: 56
                    )
                )
                .frame(width: 104, height: 104)
                .overlay(
                    Circle()
                        .strokeBorder(skin.dialEdge.opacity(0.35), lineWidth: 2)
                )
                .shadow(color: skin.dialEdge.opacity(0.32), radius: 0, y: 5)
                .shadow(color: Color.black.opacity(0.14), radius: 8, y: 5)

            // Inner Glossy Cap
            Circle()
                .fill(
                    RadialGradient(
                        colors: skin.dialInnerColors,
                        center: UnitPoint(x: 0.35, y: 0.28),
                        startRadius: 2,
                        endRadius: 44
                    )
                )
                .frame(width: 78, height: 78)

            // Indicator Dot at Top
            Circle()
                .fill(manager.isRunning && manager.isHealthy ? Color(hex: 0x1CC978) : skin.ink)
                .frame(width: 8, height: 8)
                .offset(y: -30)

            VStack(spacing: 2) {
                Text(":\(manager.effectivePort)")
                    .font(.system(size: 16, weight: .black, design: .monospaced))
                    .foregroundColor(skin.ink)
                Text(manager.isRunning && manager.isHealthy ? "ON AIR" : (manager.isStarting ? "BOOT" : "READY"))
                    .font(.system(size: 9.5, weight: .black, design: .rounded))
                    .foregroundColor(skin.inkSub)
            }
            .offset(y: 4)
        }
    }

    // MARK: - 4 Tactile Pastel Stat Keycap Tiles

    private var statsRow: some View {
        HStack(spacing: 12) {
            statTile(
                title: "已拆解语料",
                value: "\(manager.dbStats.episodeCount) 篇",
                icon: "film.fill",
                badgeBg: skin.skySoft,
                badgeFg: skin.sky
            )
            statTile(
                title: "生词本收藏",
                value: "\(manager.dbStats.vocabCount) 词",
                icon: "bookmark.fill",
                badgeBg: skin.keycapBg,
                badgeFg: skin.keycapInk
            )
            statTile(
                title: "运行环境状态",
                value: manager.envReport.allReady
                    ? "全部就绪"
                    : (manager.envReport.coreReady ? "核心就绪" : "缺少依赖"),
                icon: "checkmark.shield.fill",
                badgeBg: manager.envReport.coreReady ? skin.mintSoft : skin.coralSoft,
                badgeFg: manager.envReport.coreReady ? skin.mintInk : skin.coral
            )
            statTile(
                title: "大模型连接",
                value: manager.engineSettings.hasLLMKey ? "已绑定密钥" : "离线模式",
                icon: "sparkles",
                badgeBg: manager.engineSettings.hasLLMKey ? skin.accentSoft : skin.panelBg,
                badgeFg: skin.ink
            )
        }
    }

    private func statTile(title: String, value: String, icon: String, badgeBg: Color, badgeFg: Color) -> some View {
        LingoCard(skin: skin, padding: 14) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 7) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(badgeBg)
                            .frame(width: 26, height: 26)
                        Image(systemName: icon)
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(badgeFg)
                    }
                    Text(title)
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .foregroundColor(skin.inkMuted)
                }
                Text(value)
                    .font(.system(size: 18, weight: .black, design: .rounded))
                    .foregroundColor(skin.ink)
            }
        }
    }

    // MARK: - Publish & Security Config Card

    private var publishConfigCard: some View {
        LingoCard(skin: skin, padding: 20) {
            VStack(alignment: .leading, spacing: 15) {
                HStack {
                    Text("基础发布与安全设置")
                        .font(.system(size: 16, weight: .black, design: .rounded))
                        .foregroundColor(skin.ink)
                    Spacer()
                    LingoPill(skin: skin, text: "修改端口后需重启服务生效", tone: .keycap)
                }

                Divider()

                LingoFormRow(skin: skin, label: "监听端口", hint: "范围 1024 - 65535，默认 8000") {
                    LingoInputWell(skin: skin) {
                        TextField("8000", text: $portText)
                            .font(.system(size: 13.5, weight: .bold, design: .monospaced))
                    }
                    .frame(width: 130)
                }

                LingoFormRow(skin: skin, label: "局域网共享", hint: "开启后允许同 Wi-Fi 下的 iPad / 手机访问学习机") {
                    VStack(alignment: .leading, spacing: 8) {
                        Toggle("允许局域网设备访问 (0.0.0.0)", isOn: $lanAccess)
                            .toggleStyle(Lingo3DToggleStyle(skin: skin))

                        if lanAccess {
                            HStack(spacing: 10) {
                                Image(systemName: "wifi")
                                    .font(.system(size: 12.5, weight: .bold))
                                    .foregroundColor(skin.sky)

                                if let lanURL = manager.lanPreviewURL(port: draftPort) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(lanURL)
                                            .font(.system(size: 13.5, weight: .black, design: .monospaced))
                                            .foregroundColor(skin.sky)
                                            .textSelection(.enabled)
                                        Text(
                                            isLanLiveAndActive
                                                ? "已生效：同 Wi-Fi 下的平板 / 手机浏览器直接输入此地址"
                                                : (manager.isRunning
                                                    ? "请点右侧「立即应用并重启」后，同 Wi-Fi 设备即可访问"
                                                    : "保存或启动服务后，同 Wi-Fi 平板 / 手机输入此地址访问")
                                        )
                                        .font(.system(size: 11.5, weight: .semibold, design: .rounded))
                                        .foregroundColor(skin.inkSub)
                                    }

                                    Spacer(minLength: 6)

                                    if manager.isRunning && !isLanLiveAndActive {
                                        Button("立即应用并重启") {
                                            let updated = draftDesktopConfig
                                            portText = String(updated.port)
                                            Task { await manager.saveDesktopConfigAndApply(updated) }
                                        }
                                        .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .darkAccent, compact: true))
                                        .disabled(manager.isStarting || manager.isInstalling)
                                    }

                                    Button("复制地址") {
                                        copyToPasteboard(lanURL)
                                        manager.showToast("已复制局域网地址：\(lanURL)")
                                    }
                                    .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white, compact: true))
                                } else {
                                    Text("暂未检测到本机局域网 IP，请先将 Mac 连接 Wi-Fi 或网线")
                                        .font(.system(size: 12, weight: .bold, design: .rounded))
                                        .foregroundColor(skin.inkSub)
                                    Spacer(minLength: 6)
                                    Button("刷新检测") {
                                        manager.refreshLANIP()
                                    }
                                    .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white, compact: true))
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 10)
                            .background(
                                RoundedRectangle(cornerRadius: 12, style: .continuous)
                                    .fill(skin.skySoft.opacity(0.7))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                                            .strokeBorder(skin.sky.opacity(0.32), lineWidth: 1.5)
                                    )
                            )
                        }
                    }
                }


                LingoFormRow(skin: skin, label: "访问口令", hint: "可选；设置后打开学习机网页需先输入口令解锁") {
                    LingoInputWell(skin: skin) {
                        SecureField("留空表示本机免密直接进入", text: $accessPassword)
                    }
                    .frame(maxWidth: 300)
                }

                LingoFormRow(skin: skin, label: "国内加速镜像", hint: "开启后使用 hf-mirror.com 与清华镜像加速下载 Whisper 模型与依赖") {
                    Toggle("启用国内下载加速镜像", isOn: $hfMirror)
                        .toggleStyle(Lingo3DToggleStyle(skin: skin))
                }

                LingoFormRow(skin: skin, label: "自动拉起服务", hint: "下次打开 Lingo 桌面程序时自动在后台启动学习机服务") {
                    Toggle("启动桌面程序时自动启动学习机", isOn: $autoStartService)
                        .toggleStyle(Lingo3DToggleStyle(skin: skin))
                }

                Divider()

                HStack {
                    Spacer()
                    Button("还原") {
                        syncFromManager()
                    }
                    .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white))

                    Button("保存发布配置") {
                        let parsedPort = Int(portText.trimmingCharacters(in: .whitespacesAndNewlines))
                            ?? LingoReelConstants.defaultPort
                        let clamped = DesktopConfig.clampPort(parsedPort)
                        portText = String(clamped)
                        let updated = DesktopConfig(
                            port: clamped,
                            lanAccess: lanAccess,
                            accessPassword: accessPassword,
                            hfMirror: hfMirror,
                            autoStartService: autoStartService
                        )
                        manager.saveDesktopConfig(updated)
                    }
                    .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .darkAccent))
                }
            }
        }
    }

    private func copyToPasteboard(_ text: String) {
        let pb = NSPasteboard.general
        pb.clearContents()
        pb.setString(text, forType: .string)
    }
}
