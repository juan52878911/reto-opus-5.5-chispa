// swift-tools-version:5.9
import PackageDescription

// El xcframework de gomobile (gomobile bind -target=ios) va en Frameworks/Chispamovil.xcframework; no está en git:
// ver README.md. Sin él, `swift build` falla al resolver el binaryTarget.
let package = Package(
    name: "Chispa",
    platforms: [.iOS(.v15), .macOS(.v12)],
    products: [
        .library(name: "Chispa", targets: ["Chispa"]),
    ],
    dependencies: [
        // ONNX Runtime con la API ObjC/Swift (módulo OnnxRuntimeBindings) y el EP de CoreML.
        .package(url: "https://github.com/microsoft/onnxruntime-swift-package-manager.git", from: "1.19.2"),
    ],
    targets: [
        .binaryTarget(name: "Chispamovil", path: "Frameworks/Chispamovil.xcframework"),
        .target(
            name: "Chispa",
            dependencies: [
                "Chispamovil",
                .product(name: "onnxruntime", package: "onnxruntime-swift-package-manager"),
            ]
        ),
        .testTarget(name: "ChispaTests", dependencies: ["Chispa"]),
    ]
)
