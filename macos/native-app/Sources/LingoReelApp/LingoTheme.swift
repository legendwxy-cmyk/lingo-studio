import AppKit
import SwiftUI

// MARK: - Color Hex Helper

extension Color {
    init(hex: UInt32, alpha: Double = 1.0) {
        let r = Double((hex >> 16) & 0xFF) / 255.0
        let g = Double((hex >> 8) & 0xFF) / 255.0
        let b = Double(hex & 0xFF) / 255.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }
}

// MARK: - Playful 3D Tactile Skins (100% matching frontend/src/styles/tokens.css)

enum LingoSkin: String, CaseIterable, Identifiable {
    case citrus
    case lavender
    case ceramic

    var id: String { rawValue }

    var label: String {
        switch self {
        case .citrus: return "柑橘旋钮机"
        case .lavender: return "薰衣草工坊"
        case .ceramic: return "奶油陶瓷台"
        }
    }

    var dotColor: Color {
        switch self {
        case .citrus: return Color(hex: 0xFF7A2D)
        case .lavender: return Color(hex: 0xB5A1FF)
        case .ceramic: return Color(hex: 0xEAE7DF)
        }
    }

    var shellBg: Color {
        switch self {
        case .citrus: return Color(hex: 0xFF7A2D)
        case .lavender: return Color(hex: 0xB5A1FF)
        case .ceramic: return Color(hex: 0xE7E3DA)
        }
    }

    var shellDeckTop: Color {
        switch self {
        case .citrus: return Color(hex: 0xFF8E47)
        case .lavender: return Color(hex: 0xC4B3FF)
        case .ceramic: return Color(hex: 0xF7F5F0)
        }
    }

    var shellDeckBottom: Color {
        switch self {
        case .citrus: return Color(hex: 0xFF7224)
        case .lavender: return Color(hex: 0xA68EFF)
        case .ceramic: return Color(hex: 0xE8E4DC)
        }
    }

    var shellDeep: Color {
        switch self {
        case .citrus: return Color(hex: 0xC44908)
        case .lavender: return Color(hex: 0x6E52D4)
        case .ceramic: return Color(hex: 0xBDB7AA)
        }
    }

    var shellWell: Color {
        switch self {
        case .citrus: return Color(hex: 0xFFF5E4, alpha: 0.28)
        case .lavender: return Color.white.opacity(0.28)
        case .ceramic: return Color(hex: 0x171A21, alpha: 0.06)
        }
    }

    var shellPillBg: Color {
        switch self {
        case .citrus: return Color(hex: 0xFFF8EB, alpha: 0.96)
        case .lavender: return Color.white.opacity(0.96)
        case .ceramic: return .white
        }
    }

    var shellPillDeep: Color {
        switch self {
        case .citrus: return Color(hex: 0xC45312)
        case .lavender: return Color(hex: 0x7B62D8)
        case .ceramic: return Color(hex: 0xC4BFB3)
        }
    }

    var panelBg: Color {
        switch self {
        case .citrus: return Color(hex: 0xFFF6E8)
        case .lavender: return Color(hex: 0xF9F7FF)
        case .ceramic: return Color(hex: 0xF7F5F0)
        }
    }

    var panelDeep: Color {
        switch self {
        case .citrus: return Color(hex: 0xC45312)
        case .lavender: return Color(hex: 0x7B62D8)
        case .ceramic: return Color(hex: 0xBDB7AA)
        }
    }

    var cardBg: Color { .white }

    var cardDeep: Color {
        switch self {
        case .citrus: return Color(hex: 0xDECBB0)
        case .lavender: return Color(hex: 0xCFC3F2)
        case .ceramic: return Color(hex: 0xCDC8BC)
        }
    }

    var cream: Color {
        switch self {
        case .citrus: return Color(hex: 0xFFF8EB)
        case .lavender: return .white
        case .ceramic: return .white
        }
    }

    var creamDeep: Color {
        switch self {
        case .citrus: return Color(hex: 0xC4631B)
        case .lavender: return Color(hex: 0x856FD8)
        case .ceramic: return Color(hex: 0xC4BFB3)
        }
    }

    var ink: Color {
        switch self {
        case .citrus: return Color(hex: 0x1B1330)
        case .lavender: return Color(hex: 0x1A1230)
        case .ceramic: return Color(hex: 0x171A21)
        }
    }

    var inkDeep: Color {
        switch self {
        case .citrus, .lavender: return Color(hex: 0x090512)
        case .ceramic: return Color(hex: 0x07080B)
        }
    }

    var inkSub: Color {
        switch self {
        case .citrus: return Color(hex: 0x473C5C)
        case .lavender: return Color(hex: 0x3A2E59)
        case .ceramic: return Color(hex: 0x434957)
        }
    }

    var inkMuted: Color {
        switch self {
        case .citrus: return Color(hex: 0x6A5C7F)
        case .lavender: return Color(hex: 0x5B4C80)
        case .ceramic: return Color(hex: 0x5C6374)
        }
    }

    var accent: Color {
        switch self {
        case .citrus: return Color(hex: 0xFFE24C)
        case .lavender: return Color(hex: 0xD4FF3F)
        case .ceramic: return Color(hex: 0xFFE14A)
        }
    }

    var accentDeep: Color {
        switch self {
        case .citrus: return Color(hex: 0xC49B00)
        case .lavender: return Color(hex: 0x85AD00)
        case .ceramic: return Color(hex: 0xBD9900)
        }
    }

    var accentSoft: Color {
        switch self {
        case .citrus: return Color(hex: 0xFFF9CE)
        case .lavender: return Color(hex: 0xF4FFBE)
        case .ceramic: return Color(hex: 0xFFF7BD)
        }
    }

    var mint: Color { Color(hex: 0x53D89A) }
    var mintSoft: Color { Color(hex: 0xD7F8E8) }
    var mintInk: Color { Color(hex: 0x0B3320) }
    var mintDeep: Color { Color(hex: 0x1E8A58) }

    var coral: Color { Color(hex: 0xE02850) }
    var coralSoft: Color { Color(hex: 0xFFE4E9) }
    var coralDeep: Color { Color(hex: 0x8F102D) }

    var sky: Color { Color(hex: 0x1E6FC8) }
    var skySoft: Color { Color(hex: 0xE0F1FF) }
    var skyDeep: Color { Color(hex: 0x134A8A) }

    var keycapBg: Color {
        switch self {
        case .citrus: return Color(hex: 0xFFF0D4)
        case .lavender: return Color(hex: 0xEDE7FF)
        case .ceramic: return Color(hex: 0xEEF2FF)
        }
    }

    var keycapInk: Color {
        switch self {
        case .citrus: return Color(hex: 0x542204)
        case .lavender: return Color(hex: 0x2A1666)
        case .ceramic: return Color(hex: 0x162B85)
        }
    }

    var keycapDeep: Color {
        switch self {
        case .citrus: return Color(hex: 0xD48A3B)
        case .lavender: return Color(hex: 0x967EEB)
        case .ceramic: return Color(hex: 0x8AA0E6)
        }
    }

    var dialOuterColors: [Color] {
        switch self {
        case .citrus: return [Color(hex: 0xFFF7E8), Color(hex: 0xFFD699), Color(hex: 0xDF7E22)]
        case .lavender: return [.white, Color(hex: 0xE7DEFF), Color(hex: 0x8E74EB)]
        case .ceramic: return [.white, Color(hex: 0xEFECE5), Color(hex: 0xBDB7AA)]
        }
    }

    var dialInnerColors: [Color] {
        switch self {
        case .citrus: return [.white, Color(hex: 0xFFE9C4), Color(hex: 0xF3B773)]
        case .lavender: return [.white, Color(hex: 0xF3EEFF), Color(hex: 0xC8B8FF)]
        case .ceramic: return [.white, Color(hex: 0xF7F5F0), Color(hex: 0xDCD7CB)]
        }
    }

    var dialEdge: Color {
        switch self {
        case .citrus: return Color(hex: 0xA4400A)
        case .lavender: return Color(hex: 0x5C3FC0)
        case .ceramic: return Color(hex: 0x9A9386)
        }
    }
}

@MainActor
final class ThemeStore: ObservableObject {
    private static let key = "lingo_desktop_skin"

    @Published var skin: LingoSkin {
        didSet {
            UserDefaults.standard.set(skin.rawValue, forKey: Self.key)
        }
    }

    init() {
        if let raw = UserDefaults.standard.string(forKey: Self.key),
           let parsed = LingoSkin(rawValue: raw)
        {
            self.skin = parsed
        } else {
            self.skin = .citrus
        }
    }
}

// MARK: - Brand Asset Loader (Frameless 3D Lingo Wordmark)

enum LingoBrandAssets {
    static let wordmarkNSImage: NSImage? = {
        if let url = Bundle.main.url(forResource: "lingo-logo", withExtension: "png"),
           let img = NSImage(contentsOf: url)
        {
            return img
        }
        #if SWIFT_PACKAGE
        if let url = Bundle.module.url(forResource: "lingo-logo", withExtension: "png"),
           let img = NSImage(contentsOf: url)
        {
            return img
        }
        #endif
        return nil
    }()
}

struct LingoWordmarkView: View {
    var height: CGFloat = 38

    var body: some View {
        if let nsImg = LingoBrandAssets.wordmarkNSImage {
            Image(nsImage: nsImg)
                .resizable()
                .interpolation(.high)
                .aspectRatio(contentMode: .fit)
                .frame(height: height)
                .shadow(color: Color(hex: 0x1B1330, alpha: 0.20), radius: 5, y: 3)
        } else {
            Text("Lingo")
                .font(.system(size: height * 0.72, weight: .black, design: .rounded))
                .foregroundColor(Color(hex: 0x1B1330))
        }
    }
}

// MARK: - Playful 3D Tactile Button Style

enum LingoButtonVariant {
    case dark
    case darkAccent
    case mint
    case accent
    case coral
    case cream
    case white
    case keycap
}

struct Lingo3DButtonStyle: ButtonStyle {
    let skin: LingoSkin
    let variant: LingoButtonVariant
    var compact: Bool = false
    var fullWidth: Bool = false

    func makeBody(configuration: Configuration) -> some View {
        StyledButtonBody(
            configuration: configuration,
            skin: skin,
            variant: variant,
            compact: compact,
            fullWidth: fullWidth
        )
    }

    private struct StyledButtonBody: View {
        let configuration: Configuration
        let skin: LingoSkin
        let variant: LingoButtonVariant
        let compact: Bool
        let fullWidth: Bool
        @Environment(\.isEnabled) private var isEnabled

        private var palette: (bg: Color, fg: Color, deep: Color, topHighlight: Color) {
            switch variant {
            case .dark:
                return (skin.ink, .white, skin.inkDeep, Color.white.opacity(0.18))
            case .darkAccent:
                return (skin.ink, skin.accent, skin.inkDeep, Color.white.opacity(0.18))
            case .mint:
                return (skin.mint, skin.mintInk, skin.mintDeep, Color.white.opacity(0.45))
            case .accent:
                return (skin.accent, skin.ink, skin.accentDeep, Color.white.opacity(0.55))
            case .coral:
                return (skin.coral, .white, skin.coralDeep, Color.white.opacity(0.28))
            case .cream:
                return (skin.shellPillBg, skin.ink, skin.shellPillDeep, Color.white.opacity(0.90))
            case .white:
                return (.white, skin.ink, skin.cardDeep, Color.white)
            case .keycap:
                return (skin.keycapBg, skin.keycapInk, skin.keycapDeep, Color.white.opacity(0.75))
            }
        }

        var body: some View {
            let p = palette
            let radius: CGFloat = compact ? 12 : 15
            let depth: CGFloat = compact ? 3 : 4
            let pressed = configuration.isPressed && isEnabled

            configuration.label
                .font(.system(size: compact ? 12.5 : 13.5, weight: .heavy, design: .rounded))
                .foregroundColor(p.fg)
                .padding(.horizontal, compact ? 12 : 16)
                .padding(.vertical, compact ? 7 : 10)
                .frame(maxWidth: fullWidth ? .infinity : nil)
                .background(
                    ZStack {
                        RoundedRectangle(cornerRadius: radius, style: .continuous)
                            .fill(p.deep)
                            .offset(y: pressed ? 1 : depth)
                        RoundedRectangle(cornerRadius: radius, style: .continuous)
                            .fill(p.bg)
                            .overlay(
                                RoundedRectangle(cornerRadius: radius, style: .continuous)
                                    .strokeBorder(p.topHighlight, lineWidth: 1.5)
                            )
                    }
                )
                .offset(y: pressed ? depth - 1 : 0)
                .padding(.bottom, depth)
                .opacity(isEnabled ? 1.0 : 0.52)
                .animation(.spring(response: 0.18, dampingFraction: 0.72), value: pressed)
                .contentShape(Rectangle())
        }
    }
}

// MARK: - Playful 3D Tactile Toggle Switch (Exact match to Web App switches)

struct Lingo3DToggleStyle: ToggleStyle {
    let skin: LingoSkin

    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 10) {
            Button {
                withAnimation(.spring(response: 0.24, dampingFraction: 0.72)) {
                    configuration.isOn.toggle()
                }
            } label: {
                ZStack(alignment: configuration.isOn ? .trailing : .leading) {
                    Capsule(style: .continuous)
                        .fill(configuration.isOn ? Color(hex: 0x1FB671) : skin.ink)
                        .frame(width: 48, height: 26)
                        .overlay(
                            Capsule(style: .continuous)
                                .strokeBorder(Color.black.opacity(0.18), lineWidth: 1.5)
                        )
                        .shadow(color: Color.black.opacity(0.12), radius: 2, y: 1)

                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [.white, Color(hex: 0xF2EDE4)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 20, height: 20)
                        .shadow(color: Color.black.opacity(0.24), radius: 2, y: 1.5)
                        .padding(3)
                }
            }
            .buttonStyle(.plain)

            configuration.label
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundColor(skin.ink)
        }
    }
}

// MARK: - Playful 3D Tactile Card & Highlight Card

struct LingoCard<Content: View>: View {
    let skin: LingoSkin
    var highlight: Bool = false
    var padding: CGFloat = 18
    @ViewBuilder let content: () -> Content

    var body: some View {
        let bg = highlight ? skin.accent : skin.cardBg
        let deep = highlight ? skin.accentDeep : skin.cardDeep

        content()
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                ZStack {
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .fill(deep)
                        .offset(y: 4)
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .fill(bg)
                        .overlay(
                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .strokeBorder(
                                    highlight ? Color.white.opacity(0.55) : deep.opacity(0.55),
                                    lineWidth: 1.2
                                )
                        )
                }
            )
            .padding(.bottom, 4)
    }
}

// MARK: - Tactile Pill Badge

enum LingoPillTone {
    case dark
    case mint
    case coral
    case sky
    case accent
    case keycap
}

struct LingoPill: View {
    let skin: LingoSkin
    let text: String
    var tone: LingoPillTone = .dark
    var mono: Bool = false

    private var colors: (bg: Color, fg: Color) {
        switch tone {
        case .dark: return (skin.ink, .white)
        case .mint: return (skin.mintSoft, skin.mintInk)
        case .coral: return (skin.coralSoft, skin.coral)
        case .sky: return (skin.skySoft, skin.sky)
        case .accent: return (skin.accent, skin.ink)
        case .keycap: return (skin.keycapBg, skin.keycapInk)
        }
    }

    var body: some View {
        let c = colors
        Text(text)
            .font(
                mono
                    ? .system(size: 11.5, weight: .bold, design: .monospaced)
                    : .system(size: 11.5, weight: .heavy, design: .rounded)
            )
            .foregroundColor(c.fg)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(
                Capsule(style: .continuous)
                    .fill(c.bg)
            )
    }
}

// MARK: - Tactile Input Field Well (Crisp contrast regardless of system theme)

struct LingoInputWell<Content: View>: View {
    let skin: LingoSkin
    @ViewBuilder let content: () -> Content

    var body: some View {
        content()
            .textFieldStyle(.plain)
            .font(.system(size: 13, weight: .medium, design: .rounded))
            .foregroundColor(skin.ink)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(skin.panelBg)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .strokeBorder(skin.cardDeep, lineWidth: 1.6)
                    )
            )
    }
}

// MARK: - 3-Dot Tactile Skin Switcher (Exact twin of Web TopBar)

struct LingoSkinDots: View {
    @ObservedObject var theme: ThemeStore

    var body: some View {
        HStack(spacing: 6) {
            ForEach(LingoSkin.allCases) { s in
                Button {
                    withAnimation(.easeInOut(duration: 0.22)) {
                        theme.skin = s
                    }
                } label: {
                    Circle()
                        .fill(s.dotColor)
                        .frame(width: 20, height: 20)
                        .overlay(
                            Circle()
                                .strokeBorder(
                                    theme.skin == s ? theme.skin.ink : Color.black.opacity(0.18),
                                    lineWidth: theme.skin == s ? 2.5 : 1
                                )
                        )
                        .shadow(color: Color.black.opacity(0.18), radius: 1.5, y: 1.5)
                        .scaleEffect(theme.skin == s ? 1.1 : 1.0)
                }
                .buttonStyle(.plain)
                .help("切换外壳皮肤：\(s.label)")
            }
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 6)
        .background(
            ZStack {
                Capsule(style: .continuous)
                    .fill(theme.skin.shellPillDeep)
                    .offset(y: 3)
                Capsule(style: .continuous)
                    .fill(theme.skin.shellPillBg)
            }
        )
        .padding(.bottom, 3)
    }
}

// MARK: - Form Row Layout Helper

struct LingoFormRow<Content: View>: View {
    let skin: LingoSkin
    let label: String
    let hint: String
    @ViewBuilder let content: () -> Content

    var body: some View {
        HStack(alignment: .center, spacing: 18) {
            VStack(alignment: .leading, spacing: 3) {
                Text(label)
                    .font(.system(size: 13.5, weight: .heavy, design: .rounded))
                    .foregroundColor(skin.ink)
                Text(hint)
                    .font(.system(size: 11.5, weight: .medium, design: .rounded))
                    .foregroundColor(skin.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(width: 245, alignment: .leading)

            content()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
