import AppKit
import LingoReelCore
import SwiftUI

enum ConsoleTab: String, CaseIterable, Identifiable {
    case overview = "服务总览"
    case environment = "环境与依赖"
    case aiSettings = "AI 模型"
    case logs = "运行日志"

    var id: String { rawValue }

    var symbol: String {
        switch self {
        case .overview: return "play.circle.fill"
        case .environment: return "shippingbox.fill"
        case .aiSettings: return "sparkles"
        case .logs: return "terminal.fill"
        }
    }
}

struct MainView: View {
    @ObservedObject var manager: ServiceManager
    @ObservedObject var theme: ThemeStore
    let onOpenWebApp: () -> Void
    let onQuitApp: () -> Void

    @State private var selectedTab: ConsoleTab = .overview

    private var skin: LingoSkin { theme.skin }

    var body: some View {
        ZStack(alignment: .bottom) {
            // Outer Playful 3D Tactile Chassis Shell (Citrus / Lavender / Ceramic)
            LinearGradient(
                colors: [skin.shellDeckTop, skin.shellBg, skin.shellDeckBottom],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            VStack(spacing: 12) {
                topChassisBar
                innerStudioStage
            }
            .padding(.top, 10)
            .padding(.horizontal, 16)
            .padding(.bottom, 16)

            if !manager.toastMessage.isEmpty {
                toastBanner
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .padding(.bottom, 26)
            }
        }
        .frame(minWidth: 920, minHeight: 640)
        .animation(.spring(response: 0.28, dampingFraction: 0.8), value: manager.toastMessage)
    }

    // MARK: - Top Chassis Header Bar (Mirrors Web TopBar.jsx)

    private var topChassisBar: some View {
        HStack(spacing: 12) {
            // Clearance for macOS traffic-light window controls + frameless 3D Lingo wordmark
            HStack(spacing: 10) {
                Spacer().frame(width: 66)

                Button {
                    selectedTab = .overview
                } label: {
                    LingoWordmarkView(height: 36)
                }
                .buttonStyle(.plain)
                .help("Lingo 原生桌面控制台")

                statusPill
            }

            Spacer(minLength: 8)

            // Recessed Center Navigation Pill Well (exact Web App signature)
            HStack(spacing: 6) {
                ForEach(ConsoleTab.allCases) { tab in
                    navTabButton(tab)
                }
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(skin.shellWell)
                    .overlay(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .strokeBorder(Color.black.opacity(0.08), lineWidth: 1)
                    )
            )

            Spacer(minLength: 8)

            // Right Utility Rack: 3-Skin Switcher + Open Learning Machine + Quit
            HStack(spacing: 8) {
                LingoSkinDots(theme: theme)

                Button(action: onOpenWebApp) {
                    HStack(spacing: 5) {
                        Image(systemName: "safari.fill")
                            .font(.system(size: 12.5, weight: .bold))
                        Text("打开学习机")
                    }
                }
                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .mint, compact: true))
                .disabled(manager.isInstalling || !manager.envReport.coreReady)
                .help("在默认浏览器打开 Lingo 学习机")

                Button(action: onQuitApp) {
                    Image(systemName: "power")
                        .font(.system(size: 12.5, weight: .black))
                }
                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .cream, compact: true))
                .help("退出 Lingo 控制台与后台服务")
            }
        }
        .padding(.top, 2)
    }

    private var statusPill: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(statusDotColor)
                .frame(width: 9, height: 9)
                .shadow(color: statusDotColor.opacity(0.6), radius: 3)
            Text(manager.statusSummary)
                .font(.system(size: 12, weight: .heavy, design: .rounded))
                .foregroundColor(skin.ink)
            if manager.isRunning {
                Text(":\(manager.effectivePort)")
                    .font(.system(size: 11.5, weight: .bold, design: .monospaced))
                    .foregroundColor(skin.inkSub)
            }
        }
        .padding(.horizontal, 11)
        .padding(.vertical, 6)
        .background(
            ZStack {
                Capsule(style: .continuous)
                    .fill(skin.shellPillDeep)
                    .offset(y: 3)
                Capsule(style: .continuous)
                    .fill(skin.shellPillBg)
            }
        )
        .padding(.bottom, 3)
    }

    private func navTabButton(_ tab: ConsoleTab) -> some View {
        let isSelected = selectedTab == tab
        let badge: String? = {
            if tab == .environment && !manager.envReport.items.isEmpty && !manager.envReport.coreReady {
                return "缺依赖"
            }
            if tab == .logs && !manager.logs.isEmpty {
                return "\(manager.logs.count)"
            }
            return nil
        }()

        return Button {
            selectedTab = tab
            if tab == .aiSettings {
                manager.reloadEngineSettings()
            } else if tab == .environment {
                Task { await manager.refreshEnvironment() }
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: tab.symbol)
                    .font(.system(size: 12.5, weight: .bold))
                Text(tab.rawValue)
                    .font(.system(size: 12.5, weight: .heavy, design: .rounded))
                if let badge {
                    Text(badge)
                        .font(.system(size: 10, weight: .black, design: .rounded))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1.5)
                        .background(
                            Capsule(style: .continuous)
                                .fill(tab == .environment ? skin.accent : skin.mint)
                        )
                        .foregroundColor(skin.ink)
                }
            }
        }
        .buttonStyle(
            Lingo3DButtonStyle(
                skin: skin,
                variant: isSelected ? .darkAccent : .cream,
                compact: true
            )
        )
    }

    // MARK: - Inner Warm Cream Studio Stage (Exact Web Panel Frame)

    private var innerStudioStage: some View {
        VStack(spacing: 0) {
            if !manager.lastErrorBanner.isEmpty {
                HStack(spacing: 10) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(skin.coral)
                    Text(manager.lastErrorBanner)
                        .font(.system(size: 12.5, weight: .bold, design: .rounded))
                        .foregroundColor(skin.ink)
                        .lineLimit(2)
                    Spacer()
                    Button("查看日志") { selectedTab = .logs }
                        .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white, compact: true))
                    Button {
                        manager.lastErrorBanner = ""
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 11, weight: .black))
                            .foregroundColor(skin.inkSub)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 10)
                .background(skin.coralSoft)
                Divider()
            }

            Group {
                switch selectedTab {
                case .overview:
                    OverviewTab(
                        manager: manager,
                        skin: skin,
                        onOpenWebApp: onOpenWebApp,
                        onGoEnvironment: { selectedTab = .environment }
                    )
                case .environment:
                    EnvironmentTab(
                        manager: manager,
                        skin: skin,
                        onGoLogs: { selectedTab = .logs }
                    )
                case .aiSettings:
                    AISettingsTab(manager: manager, skin: skin)
                case .logs:
                    LogsTab(manager: manager, skin: skin)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .background(
            ZStack {
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .fill(skin.panelDeep)
                    .offset(y: 6)
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .fill(skin.panelBg)
                    .overlay(
                        RoundedRectangle(cornerRadius: 24, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.85), lineWidth: 2)
                    )
            }
            .shadow(color: Color.black.opacity(0.14), radius: 14, y: 10)
        )
        .padding(.bottom, 6)
    }

    private var toastBanner: some View {
        HStack(spacing: 8) {
            Image(systemName: manager.toastIsError ? "xmark.circle.fill" : "checkmark.circle.fill")
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(manager.toastIsError ? Color(hex: 0xFF6B8A) : skin.mint)
            Text(manager.toastMessage)
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundColor(.white)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 11)
        .background(
            ZStack {
                Capsule(style: .continuous)
                    .fill(skin.inkDeep)
                    .offset(y: 3)
                Capsule(style: .continuous)
                    .fill(skin.ink)
            }
            .shadow(color: Color.black.opacity(0.28), radius: 12, y: 6)
        )
    }

    private var statusDotColor: Color {
        if manager.isInstalling || manager.isStarting { return Color(hex: 0xFF9F1C) }
        if manager.isRunning && manager.isHealthy { return Color(hex: 0x1CC978) }
        if manager.isRunning { return Color(hex: 0xF5C400) }
        return Color(hex: 0x9CA3AF)
    }
}
