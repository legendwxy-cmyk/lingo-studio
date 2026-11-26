// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Lingo",
    platforms: [
        .macOS(.v12),
    ],
    products: [
        .library(name: "LingoReelCore", targets: ["LingoReelCore"]),
        .executable(name: "LingoReelApp", targets: ["LingoReelApp"]),
    ],
    targets: [
        .target(
            name: "LingoReelCore",
            path: "Sources/LingoReelCore",
            linkerSettings: [
                .linkedLibrary("sqlite3"),
            ]
        ),
        .executableTarget(
            name: "LingoReelApp",
            dependencies: ["LingoReelCore"],
            path: "Sources/LingoReelApp",
            resources: [
                .process("Resources"),
            ],
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("SwiftUI"),
            ]
        ),
        .testTarget(
            name: "LingoReelDesktopTests",
            dependencies: ["LingoReelCore"],
            path: "Tests/LingoReelDesktopTests"
        ),
    ]
)
