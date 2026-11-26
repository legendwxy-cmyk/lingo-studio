import AppKit
import LingoReelCore
import SwiftUI

struct LogsTab: View {
    @ObservedObject var manager: ServiceManager
    let skin: LingoSkin

    @State private var searchText: String = ""
    @State private var autoScroll: Bool = true

    private var filteredLogs: [LogEntry] {
        let q = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if q.isEmpty { return manager.logs }
        return manager.logs.filter { $0.line.lowercased().contains(q) || $0.timestamp.contains(q) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("实时运行日志")
                        .font(.system(size: 22, weight: .black, design: .rounded))
                        .foregroundColor(skin.ink)
                    Text("实时展示 Lingo 后端服务与依赖安装器的全部输出，方便快速排查问题。")
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .foregroundColor(skin.inkMuted)
                }
                Spacer()
                LingoPill(skin: skin, text: "共 \(filteredLogs.count) 条", tone: .dark, mono: true)
            }

            HStack(spacing: 10) {
                LingoInputWell(skin: skin) {
                    HStack(spacing: 6) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(skin.inkMuted)
                        TextField("过滤日志关键词...", text: $searchText)
                    }
                }
                .frame(maxWidth: 260)

                Toggle("自动滚底", isOn: $autoScroll)
                    .toggleStyle(Lingo3DToggleStyle(skin: skin))

                Spacer()

                Button {
                    let full = filteredLogs.map { "[\($0.timestamp)] \($0.line)" }.joined(separator: "\n")
                    let pb = NSPasteboard.general
                    pb.clearContents()
                    pb.setString(full, forType: .string)
                    manager.showToast("已复制 \(filteredLogs.count) 条日志")
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "doc.on.doc")
                        Text("复制日志")
                    }
                }
                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white, compact: true))

                Button {
                    NSWorkspace.shared.activateFileViewerSelecting([manager.paths.logFilePath])
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "folder")
                        Text("显示文件")
                    }
                }
                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white, compact: true))

                Button("清空") {
                    manager.clearLogs()
                }
                .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .coral, compact: true))
            }

            // Deep Ink Hardware Screen (matches Web App's video screen & bottom lexicon dock)
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        ForEach(filteredLogs) { entry in
                            HStack(alignment: .top, spacing: 10) {
                                Text(entry.timestamp)
                                    .font(.system(size: 11.5, weight: .semibold, design: .monospaced))
                                    .foregroundColor(Color.white.opacity(0.45))
                                Text(entry.line)
                                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                                    .foregroundColor(lineColor(entry.line))
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .id(entry.id)
                        }
                    }
                    .padding(16)
                }
                .background(
                    ZStack {
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(skin.inkDeep)
                            .offset(y: 4)
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(skin.ink)
                            .overlay(
                                RoundedRectangle(cornerRadius: 20, style: .continuous)
                                    .strokeBorder(Color.white.opacity(0.10), lineWidth: 1.2)
                            )
                    }
                )
                .padding(.bottom, 4)
                .onChange(of: manager.logs.last?.id) { _ in
                    if autoScroll, let last = filteredLogs.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
        }
        .padding(24)
    }

    private func lineColor(_ line: String) -> Color {
        let lower = line.lowercased()
        if lower.contains("error") || lower.contains("traceback") || line.contains("[错误]") {
            return Color(hex: 0xFF7B93)
        }
        if lower.contains("warning") || line.contains("[警告]") {
            return Color(hex: 0xFFE24C)
        }
        if line.contains("[完成]") || line.contains("就绪") || line.contains("成功") {
            return Color(hex: 0x53D89A)
        }
        return Color(hex: 0xF5F2FF)
    }
}
