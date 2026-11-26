import AppKit
import LingoReelCore
import SwiftUI

struct EnvironmentTab: View {
    @ObservedObject var manager: ServiceManager
    let skin: LingoSkin
    let onGoLogs: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                headerSection
                actionBanner
                dependencyListCard
                storagePathsCard
            }
            .padding(24)
        }
        .onAppear {
            Task { await manager.refreshEnvironment() }
        }
    }

    private var headerSection: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 4) {
                Text("运行环境与依赖管理")
                    .font(.system(size: 22, weight: .black, design: .rounded))
                    .foregroundColor(skin.ink)
                Text("实时检测 Python 3.10–3.12、独立虚拟环境、FFmpeg 与离线语音模型；缺失时可直接一键全自动安装。")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundColor(skin.inkMuted)
            }
            Spacer()
            Button {
                Task { await manager.refreshEnvironment() }
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "arrow.clockwise")
                    Text(manager.isCheckingEnv ? "检测中..." : "重新检测")
                }
            }
            .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white, compact: true))
            .disabled(manager.isCheckingEnv || manager.isInstalling)
        }
    }

    private var actionBanner: some View {
        LingoCard(skin: skin, highlight: !manager.envReport.allReady && !manager.isInstalling, padding: 18) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 15, style: .continuous)
                        .fill(manager.envReport.allReady ? skin.mint : skin.ink)
                        .frame(width: 48, height: 48)
                    if manager.isInstalling {
                        ProgressView()
                            .controlSize(.small)
                            .colorInvert()
                    } else {
                        Image(systemName: manager.envReport.allReady ? "checkmark.seal.fill" : "arrow.down.circle.fill")
                            .font(.system(size: 22, weight: .bold))
                            .foregroundColor(manager.envReport.allReady ? skin.mintInk : skin.accent)
                    }
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text(bannerTitle)
                        .font(.system(size: 15.5, weight: .black, design: .rounded))
                        .foregroundColor(skin.ink)
                    Text(bannerSubtitle)
                        .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                        .foregroundColor(skin.inkSub)
                }

                Spacer()

                if manager.envReport.pythonPath == nil && !manager.isInstalling {
                    Button("手动下载 Python") {
                        if let url = URL(string: "https://www.python.org/downloads/macos/") {
                            NSWorkspace.shared.open(url)
                        }
                    }
                    .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white, compact: true))
                }

                Button {
                    Task { await manager.installDependencies() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.down.to.line")
                        Text(
                            manager.isInstalling
                                ? "正在安装依赖..."
                                : (manager.envReport.allReady ? "修复 / 更新依赖" : "一键安装全部依赖")
                        )
                    }
                }
                .buttonStyle(
                    Lingo3DButtonStyle(
                        skin: skin,
                        variant: manager.envReport.allReady ? .mint : .darkAccent
                    )
                )
                .disabled(manager.isInstalling)
            }
        }
    }

    private var dependencyListCard: some View {
        LingoCard(skin: skin, padding: 20) {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Text("依赖检查清单")
                        .font(.system(size: 16, weight: .black, design: .rounded))
                        .foregroundColor(skin.ink)
                    Spacer()
                    if manager.isInstalling {
                        Button("查看实时安装日志") { onGoLogs() }
                            .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .accent, compact: true))
                    }
                }

                if manager.envReport.items.isEmpty {
                    HStack(spacing: 10) {
                        ProgressView().controlSize(.small)
                        Text("正在扫描本机运行环境...")
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                            .foregroundColor(skin.inkMuted)
                    }
                    .padding(.vertical, 12)
                } else {
                    ForEach(manager.envReport.items) { item in
                        dependencyRow(item)
                        if item.id != manager.envReport.items.last?.id {
                            Divider()
                        }
                    }
                }
            }
        }
    }

    private func dependencyRow(_ item: DependencyItem) -> some View {
        HStack(alignment: .top, spacing: 12) {
            ZStack {
                Circle()
                    .fill(
                        item.installed
                            ? skin.mintSoft
                            : (item.required ? skin.coralSoft : skin.accentSoft)
                    )
                    .frame(width: 30, height: 30)
                Image(
                    systemName: item.installed
                        ? "checkmark"
                        : (item.required ? "xmark" : "exclamationmark")
                )
                .font(.system(size: 13, weight: .black))
                .foregroundColor(
                    item.installed
                        ? skin.mintInk
                        : (item.required ? skin.coral : skin.ink)
                )
            }
            .padding(.top, 2)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Text(item.title)
                        .font(.system(size: 14, weight: .heavy, design: .rounded))
                        .foregroundColor(skin.ink)
                    LingoPill(
                        skin: skin,
                        text: item.required ? "必需" : "推荐",
                        tone: item.required ? .sky : .keycap
                    )
                }
                Text(item.detail)
                    .font(.system(size: 12.5, weight: .medium, design: .rounded))
                    .foregroundColor(skin.inkMuted)
                if !item.path.isEmpty {
                    Text(item.path)
                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                        .foregroundColor(skin.inkSub)
                        .textSelection(.enabled)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }

            Spacer()

            LingoPill(
                skin: skin,
                text: item.installed ? (item.version.isEmpty ? "已就绪" : item.version) : "未安装",
                tone: item.installed ? .mint : (item.required ? .coral : .accent),
                mono: true
            )
        }
        .padding(.vertical, 4)
    }

    private var storagePathsCard: some View {
        LingoCard(skin: skin, padding: 20) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("本机数据与独立环境目录")
                        .font(.system(size: 16, weight: .black, design: .rounded))
                        .foregroundColor(skin.ink)
                    Spacer()
                    Button {
                        NSWorkspace.shared.open(manager.paths.dataDir)
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: "folder.fill")
                            Text("在 Finder 中打开")
                        }
                    }
                    .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white, compact: true))
                }

                Divider()

                pathRow(title: "用户数据与语料库", path: manager.paths.dataDir.path)
                pathRow(title: "独立 Python 环境", path: manager.paths.venvDir.path)
                pathRow(title: "Whisper 模型缓存", path: manager.paths.whisperCacheDir.path)
                pathRow(title: "应用资源目录", path: manager.paths.appResourcesDir.path)
            }
        }
    }

    private func pathRow(title: String, path: String) -> some View {
        HStack(spacing: 12) {
            Text(title)
                .font(.system(size: 12.5, weight: .heavy, design: .rounded))
                .foregroundColor(skin.ink)
                .frame(width: 132, alignment: .leading)
            Text(path)
                .font(.system(size: 11.5, weight: .medium, design: .monospaced))
                .foregroundColor(skin.inkSub)
                .textSelection(.enabled)
                .lineLimit(1)
                .truncationMode(.middle)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(skin.panelBg)
                )
            Spacer()
        }
    }

    private var bannerTitle: String {
        if manager.isInstalling { return "正在全自动配置虚拟环境并安装核心依赖..." }
        if manager.envReport.allReady { return "所有运行环境与离线语音引擎均已就绪" }
        if manager.envReport.pythonPath == nil { return "未检测到系统 Python 3（3.10 - 3.12）" }
        if manager.envReport.coreReady { return "核心运行环境已就绪，可补装推荐组件" }
        return "检测到缺失核心运行依赖"
    }

    private var bannerSubtitle: String {
        if manager.isInstalling {
            return "优先使用国内清华镜像加速安装，失败自动回退官方源，可在「运行日志」查看实时进度。"
        }
        if manager.envReport.pythonPath == nil {
            return "直接点击右侧「一键安装全部依赖」将通过 uv 自动下载独立 Python 3.12 与全部组件（也可手动下载安装）。"
        }
        if manager.envReport.allReady {
            return "现可随时切回「服务总览」一键启动 Lingo 学习机。"
        }
        return "点击右侧「一键安装全部依赖」将自动配置隔离虚拟环境、FFmpeg 与本地 Faster-Whisper。"
    }
}
