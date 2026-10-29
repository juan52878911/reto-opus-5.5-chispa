import Foundation
import CryptoKit

/// Ficheros que el SDK deja en disco (ONNX de L2 y de TORR extraídos): nombrados por el hash de su contenido y escritos
/// en un temporal con `rename` atómico, de modo que un fichero con su nombre definitivo siempre está completo.
enum CacheFicheros {
    static func sha256Hex(_ datos: Data) -> String {
        SHA256.hash(data: datos).map { String(format: "%02x", $0) }.joined()
    }

    /// sha256 del fichero leído por trozos (sin cargarlo entero en memoria).
    static func sha256Hex(fichero ruta: String) throws -> String {
        guard let h = FileHandle(forReadingAtPath: ruta) else { throw ErrorChispa("no se puede leer \(ruta)") }
        defer { try? h.close() }
        var sha = SHA256()
        while let trozo = try h.read(upToCount: 1 << 16), !trozo.isEmpty { sha.update(data: trozo) }
        return sha.finalize().map { String(format: "%02x", $0) }.joined()
    }

    /// Escribe `destino` con `escribir` sobre un temporal propio y lo renombra (`rename(2)` sustituye al destino de
    /// forma atómica). Se comprueba el resultado: si falla, se lanza y el temporal se borra.
    static func escribirAtomico(_ destino: String, _ escribir: (String) throws -> Void) throws {
        let tmp = destino + ".\(UUID().uuidString).tmp"
        do {
            try escribir(tmp)
            guard rename(tmp, destino) == 0 else {
                throw ErrorChispa("no se pudo mover \(tmp) a \(destino) (errno \(errno))")
            }
        } catch {
            try? FileManager.default.removeItem(atPath: tmp)
            throw error
        }
    }

    static func existeNoVacio(_ ruta: String) -> Bool {
        let n = (try? FileManager.default.attributesOfItem(atPath: ruta))?[.size] as? NSNumber
        return (n?.intValue ?? 0) > 0
    }

    /// `chispa-l2-<hash>.onnx` en `dir`; el hash es el de la sección L2 del motor (o, si no lo da, el del `modelo`).
    /// Extrae solo si falta.
    static func rutaOnnxL2(motor: Motor, dir: URL, modelo: String) throws -> String {
        var hash = motor.hashSeccion(seccionL2)
        if hash.isEmpty { hash = try sha256Hex(fichero: modelo) }
        let onnx = dir.appendingPathComponent("chispa-l2-\(hash).onnx").path
        if !existeNoVacio(onnx) { try escribirAtomico(onnx) { try motor.extraerL2(a: $0) } }
        return onnx
    }

    /// `chispa-torre-<hash>.onnx` en `dir` con los bytes de TORR; escribe solo si falta.
    static func rutaOnnxTorre(_ onnx: Data, dir: URL) throws -> String {
        let ruta = dir.appendingPathComponent("chispa-torre-\(sha256Hex(onnx)).onnx").path
        if !existeNoVacio(ruta) { try escribirAtomico(ruta) { try onnx.write(to: URL(fileURLWithPath: $0)) } }
        return ruta
    }
}
