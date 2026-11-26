import AppKit
import Combine
import Foundation
import LingoReelCore
import SwiftUI

let lingoShowWindowNotification = Notification.Name("com.lingoreel.studio.showMainWindow")

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private var mainWindow: NSWindow?
    private var statusItem: NSStatusItem?
    private var serviceManager: ServiceManager!
    private var themeStore = ThemeStore()
    private var cancellables = Set<AnyCancellable>()

    func applicationDidFinishLaunching(_ notification: Notification) {
        serviceManager = ServiceManager(paths: .resolveDefault())
        setupMainMenu()
        setupStatusBarItem()
        setupMainWindow()
        bindStatusUpdates()
        observeSingleInstanceWake()
        serviceManager.bootstrap()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showMainWindow()
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        DistributedNotificationCenter.default().removeObserver(self)
        serviceManager?.shutdownSynchronously()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        // Keep running in the menu bar when user closes window with red X; quit via ⌘Q or menu bar.
        return false
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        sender.orderOut(nil)
        return false
    }

    private func observeSingleInstanceWake() {
        DistributedNotificationCenter.default().addObserver(
            self,
            selector: #selector(showMainWindow),
            name: lingoShowWindowNotification,
            object: nil
        )
    }

    // MARK: - Main Window (Edge-to-Edge Tactile Chassis with Transparent Titlebar)

    private func setupMainWindow() {
        let rootView = MainView(
            manager: serviceManager,
            theme: themeStore,
            onOpenWebApp: { [weak self] in self?.openWebAppInBrowser() },
            onQuitApp: { NSApp.terminate(nil) }
        )
        let hosting = NSHostingController(rootView: rootView)

        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1060, height: 720),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        win.title = "Lingo"
        win.titleVisibility = .hidden
        win.titlebarAppearsTransparent = true
        win.isMovableByWindowBackground = true
        // Keep Aqua appearance so native text inputs inside warm cream cards stay crisp dark ink even in macOS Dark Mode
        win.appearance = NSAppearance(named: .aqua)
        win.minSize = NSSize(width: 920, height: 640)
        win.isReleasedWhenClosed = false
        win.contentViewController = hosting
        win.delegate = self
        win.center()
        win.setFrameAutosaveName("LingoDesktopMainWindow")

        mainWindow = win
        showMainWindow()
    }

    @objc func showMainWindow() {
        if let win = mainWindow {
            win.makeKeyAndOrderFront(nil)
        }
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func openWebAppInBrowser() {
        if !serviceManager.isRunning {
            Task {
                await serviceManager.startService()
                if serviceManager.isRunning {
                    NSWorkspace.shared.open(serviceManager.launchBrowserURL)
                }
            }
        } else {
            NSWorkspace.shared.open(serviceManager.launchBrowserURL)
        }
    }

    @objc func toggleServiceFromTray() {
        Task {
            if serviceManager.isRunning {
                await serviceManager.stopService()
            } else {
                await serviceManager.startService()
            }
        }
    }

    @objc func quitApplication() {
        NSApp.terminate(nil)
    }

    // MARK: - Native Menu Bar (NSStatusItem)

    private func setupStatusBarItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let btn = item.button {
            if let img = NSImage(systemSymbolName: "waveform.circle.fill", accessibilityDescription: "Lingo") {
                img.isTemplate = true
                btn.image = img
            } else {
                btn.title = "Lingo"
            }
            btn.toolTip = "Lingo 桌面控制台"
        }
        statusItem = item
        rebuildStatusMenu()
    }

    private func bindStatusUpdates() {
        Publishers.CombineLatest4(
            serviceManager.$isRunning,
            serviceManager.$isHealthy,
            serviceManager.$isInstalling,
            serviceManager.$isStarting
        )
        .combineLatest(serviceManager.$config, serviceManager.$activePort)
        .receive(on: RunLoop.main)
        .sink { [weak self] _, _, _ in
            self?.rebuildStatusMenu()
        }
        .store(in: &cancellables)
    }

    private func rebuildStatusMenu() {
        guard let item = statusItem else { return }
        let menu = NSMenu()

        let statusText: String
        if serviceManager.isInstalling {
            statusText = "状态：正在安装运行依赖..."
        } else if serviceManager.isStarting {
            statusText = "状态：正在启动服务..."
        } else if serviceManager.isRunning && serviceManager.isHealthy {
            statusText = "状态：Lingo 运行中 (:\(serviceManager.effectivePort))"
        } else if serviceManager.isRunning {
            statusText = "状态：Lingo 启动中..."
        } else {
            statusText = "状态：服务已停止"
        }

        let header = NSMenuItem(title: statusText, action: nil, keyEquivalent: "")
        header.isEnabled = false
        menu.addItem(header)
        menu.addItem(.separator())

        let showItem = NSMenuItem(title: "打开 Lingo 桌面控制台", action: #selector(showMainWindow), keyEquivalent: "")
        showItem.target = self
        menu.addItem(showItem)

        let openWebItem = NSMenuItem(title: "在浏览器打开 Lingo 学习机", action: #selector(openWebAppInBrowser), keyEquivalent: "")
        openWebItem.target = self
        menu.addItem(openWebItem)

        menu.addItem(.separator())

        let toggleTitle = serviceManager.isRunning ? "停止 Lingo 服务" : "启动 Lingo 服务"
        let toggleItem = NSMenuItem(title: toggleTitle, action: #selector(toggleServiceFromTray), keyEquivalent: "")
        toggleItem.target = self
        toggleItem.isEnabled = !serviceManager.isInstalling && !serviceManager.isStarting
        menu.addItem(toggleItem)

        menu.addItem(.separator())

        let quitItem = NSMenuItem(title: "退出 Lingo", action: #selector(quitApplication), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        item.menu = menu
    }

    // MARK: - Standard macOS Main Menu (including Edit ⌘C/⌘V/⌘A/⌘Z so API keys paste natively!)

    private func setupMainMenu() {
        let mainMenu = NSMenu()

        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu(title: "Lingo")
        appMenu.addItem(withTitle: "显示 Lingo 控制台", action: #selector(showMainWindow), keyEquivalent: "0")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "隐藏 Lingo", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let hideOthers = NSMenuItem(title: "隐藏其他", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        hideOthers.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(hideOthers)
        appMenu.addItem(withTitle: "显示全部", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出 Lingo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        let editMenuItem = NSMenuItem()
        let editMenu = NSMenu(title: "编辑")
        editMenu.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: "重做", action: Selector(("redo:")), keyEquivalent: "Z")
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "拷贝", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editMenuItem.submenu = editMenu
        mainMenu.addItem(editMenuItem)

        let windowMenuItem = NSMenuItem()
        let windowMenu = NSMenu(title: "窗口")
        windowMenu.addItem(withTitle: "最小化", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "关闭窗口（最小化到菜单栏）", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        windowMenuItem.submenu = windowMenu
        mainMenu.addItem(windowMenuItem)

        NSApp.mainMenu = mainMenu
        NSApp.windowsMenu = windowMenu
    }
}
