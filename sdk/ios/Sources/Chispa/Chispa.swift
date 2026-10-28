import Foundation

/// Chispa en el iPhone: un .chispa v3 abierto con la cascada L0 → L1 → L2.
///
///     let chispa = try Chispa.abrir(ruta: Bundle.main.path(forResource: "modelo", ofType: "chispa")!)
///     let r = chispa.decidir("quiero comprar dos camisetas", [pregunta]).first!
///     // r.respuesta, r.confianza, r.capa, r.escalar
///
/// L2 (ONNX Runtime con CoreML) solo se monta si el fichero trae las secciones L2 y ESQUEMAS **y** se da un
/// `Tokenizador` de e5.
public final class Chispa {
    private let motor: Motor
    private let cascada: Cascada
    private let sesion: SesionRanuras?

    init(motor: Motor, cascada: Cascada, sesion: SesionRanuras?) {
        self.motor = motor
        self.cascada = cascada
        self.sesion = sesion
    }

    deinit { motor.cerrar() }

    /// Capas que han quedado montadas, en orden.
    public var capas: [String] { motor.capas().filter { $0 != "L2" || sesion != nil } }

    /// Abre el modelo en `ruta` (un fichero de verdad: el motor lo mapea en memoria).
    public static func abrir(ruta: String, tokenizador: Tokenizador? = nil, coreML: Bool = true) throws -> Chispa {
        guard FileManager.default.isReadableFile(atPath: ruta) else { throw ErrorChispa("no existe el modelo \(ruta)") }
        let motor = try MotorNativo.abrir(ruta: ruta)
        do {
            return try montar(motor: motor, tokenizador: tokenizador, onnx: {
                // un nombre estable (nombre y tamaño del modelo) para no extraer el ONNX en cada arranque
                let atributos = try? FileManager.default.attributesOfItem(atPath: ruta)
                let tam = (atributos?[.size] as? NSNumber)?.intValue ?? 0
                let nombre = URL(fileURLWithPath: ruta).lastPathComponent
                let onnx = FileManager.default.temporaryDirectory.appendingPathComponent("chispa-l2-\(nombre)-\(tam).onnx").path
                if !FileManager.default.fileExists(atPath: onnx) { try motor.extraerL2(a: onnx) }
                return onnx
            }, crearSesion: { try SesionOrt(rutaOnnx: $0, coreML: coreML) })
        } catch {
            motor.cerrar()
            throw error
        }
    }

    /// Monta la cascada sobre cualquier `Motor` (los tests usan uno falso). `onnx` da la ruta del ONNX de L2.
    static func montar(motor: Motor, tokenizador: Tokenizador?, onnx: () throws -> String,
                       crearSesion: (String) throws -> SesionRanuras) throws -> Chispa {
        var sesion: SesionRanuras?
        var l2: Capa?
        if motor.capas().contains("L2"), let tok = tokenizador {
            let s = try crearSesion(try onnx())
            sesion = s
            l2 = CapaL2(motor: motor, sesion: s, tokenizador: tok)
        }
        return Chispa(motor: motor, cascada: try Cascada.armar(motor: motor, l2: l2), sesion: sesion)
    }

    /// Decide cada pregunta para el `texto` (en orden). Sin conexión: todo ocurre en el dispositivo.
    public func decidir(_ texto: String, _ preguntas: [Pregunta]) -> [Respuesta] {
        preguntas.map { cascada.decidir(texto, $0) }
    }
}
