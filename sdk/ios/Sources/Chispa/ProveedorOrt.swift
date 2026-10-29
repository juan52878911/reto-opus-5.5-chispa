import Foundation
import os

/// Proveedor de ejecución de ONNX Runtime para las sesiones de L2 y de la torre. Si `coreML` falla al crear la sesión, se cae a `cpu`.
public enum ProveedorOrt: String {
    case cpu = "CPU"
    case coreML = "CoreML"
}

/// El proveedor por defecto en iOS.
public let proveedorOrtPorDefecto = ProveedorOrt.coreML

private let registroOrt = OSLog(subsystem: "com.chispa.sdk", category: "ort")

func avisarRespaldoOrt(_ mensaje: String) {
    os_log("%{public}@", log: registroOrt, type: .default, mensaje)
}

/// Abre con `proveedor` y, si `crear` lanza, lo avisa y reintenta con CPU. Devuelve lo creado y el proveedor que quedó.
/// Si CPU también falla, el error sube.
func abrirConRespaldo<T>(_ proveedor: ProveedorOrt, etiqueta: String,
                         aviso: (String) -> Void = avisarRespaldoOrt,
                         crear: (ProveedorOrt) throws -> T) throws -> (T, ProveedorOrt) {
    if proveedor == .cpu { return (try crear(.cpu), .cpu) }
    do {
        return (try crear(proveedor), proveedor)
    } catch {
        aviso("\(etiqueta): ORT con \(proveedor.rawValue) falló (\(error)); sigo con CPU")
        return (try crear(.cpu), .cpu)
    }
}
