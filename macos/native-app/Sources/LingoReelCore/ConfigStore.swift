import Foundation

public final class ConfigStore: Sendable {
    public let configURL: URL

    public init(configURL: URL) {
        self.configURL = configURL
    }

    public func load() -> DesktopConfig {
        guard let data = try? Data(contentsOf: configURL) else {
            return DesktopConfig()
        }
        guard var decoded = try? JSONDecoder().decode(DesktopConfig.self, from: data) else {
            return DesktopConfig()
        }
        decoded.port = DesktopConfig.clampPort(decoded.port)
        return decoded
    }

    public func save(_ config: DesktopConfig) throws {
        var sanitized = config
        sanitized.port = DesktopConfig.clampPort(config.port)

        let dir = configURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(sanitized)
        try data.write(to: configURL, options: .atomic)
    }
}
