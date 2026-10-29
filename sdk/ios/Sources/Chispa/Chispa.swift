import Foundation

/// Chispa en el iPhone: un .chispa v3 abierto con la cascada L0 → L1 → L2.
///
///     let chispa = try Chispa.abrir(ruta: Bundle.main.path(forResource: "modelo", ofType: "chispa")!)
///     let r = chispa.decidir("quiero comprar dos camisetas", [pregunta]).first!
///     // r.respuesta, r.confianza, r.capa, r.escalar
///
/// L0 usa la sección L0TF si el fichero la trae. L2 (ONNX Runtime con CoreML) solo se monta si el fichero trae las
/// secciones L2 y ESQUEMAS **y** hay tokenizador de e5: el de la app (`Tokenizador`) o el del motor, cargado de un
/// `.chispa-tok` (`rutaTokenizador`, el mismo que usa el servidor). Con CONJ en el fichero, L2 es L2c (cabeza conjunta).
///
/// Esquema nuevo (zero-shot): la pregunta trae sus opciones con descripciones. L1 las usa tal cual (torres de texto
/// cacheadas en el motor); L2 recibe las torres al vuelo con un `CodificadorTorre` (opcional) y el motor las cachea.
public final class Chispa {
    private let motor: Motor
    private let cascada: Cascada
    private let sesion: SesionRanuras?
    private let torreMotor: CodificadorTorreMotor? // vive tanto como Chispa; su sesión de ORT se libera con él

    init(motor: Motor, cascada: Cascada, sesion: SesionRanuras?, torreMotor: CodificadorTorreMotor? = nil) {
        self.motor = motor
        self.cascada = cascada
        self.sesion = sesion
        self.torreMotor = torreMotor
    }

    deinit { motor.cerrar() }

    /// Capas que han quedado montadas, en orden.
    public var capas: [String] { motor.capas().filter { $0 != "L2" || sesion != nil } }

    /// Abre el modelo en `ruta` (un fichero de verdad: el motor lo mapea en memoria).
    public static func abrir(ruta: String, tokenizador: Tokenizador? = nil, rutaTokenizador: String? = nil,
                             coreML: Bool = true, codificadorTorres: CodificadorTorre? = nil) throws -> Chispa {
        guard FileManager.default.isReadableFile(atPath: ruta) else { throw ErrorChispa("no existe el modelo \(ruta)") }
        let motor = try MotorNativo.abrir(ruta: ruta)
        do {
            var tok = tokenizador
            if tok == nil, let rt = rutaTokenizador {
                try motor.cargarTokenizadorE5(ruta: rt)
                tok = TokenizadorMotor(motor: motor)
            }
            return try montar(motor: motor, tokenizador: tok, onnx: {
                // un nombre estable (nombre y tamaño del modelo) para no extraer el ONNX en cada arranque
                let atributos = try? FileManager.default.attributesOfItem(atPath: ruta)
                let tam = (atributos?[.size] as? NSNumber)?.intValue ?? 0
                let nombre = URL(fileURLWithPath: ruta).lastPathComponent
                let onnx = FileManager.default.temporaryDirectory.appendingPathComponent("chispa-l2-\(nombre)-\(tam).onnx").path
                if !FileManager.default.fileExists(atPath: onnx) { try motor.extraerL2(a: onnx) }
                return onnx
            }, crearSesion: { try SesionOrt(rutaOnnx: $0, coreML: coreML) }, codificadorTorres: codificadorTorres)
        } catch {
            motor.cerrar()
            throw error
        }
    }

    /// Monta la cascada sobre cualquier `Motor` (los tests usan uno falso). `onnx` da la ruta del ONNX de L2.
    static func montar(motor: Motor, tokenizador: Tokenizador?, onnx: () throws -> String,
                       crearSesion: (String) throws -> SesionRanuras,
                       codificadorTorres: CodificadorTorre? = nil,
                       crearSesionTorre: @escaping (Data) throws -> SesionTorre = { try SesionTorreOrt(onnx: $0) }) throws -> Chispa {
        var sesion: SesionRanuras?
        var l2: Capa?
        var torreMotor: CodificadorTorreMotor?
        if motor.capas().contains("L2"), let tok = tokenizador {
            let s = try crearSesion(try onnx())
            sesion = s
            // Sin codificador de la app, y con TORR en el fichero, las torres al vuelo salen del ONNX de TORR.
            var enc = codificadorTorres
            if enc == nil, motor.tieneTorre(), motor.tieneTokenizadorE5() {
                let t = CodificadorTorreMotor(motor: motor, crearSesion: crearSesionTorre)
                torreMotor = t
                enc = t
            }
            l2 = CapaL2(motor: motor, sesion: s, tokenizador: tok, codificador: enc)
        }
        return Chispa(motor: motor, cascada: try Cascada.armar(motor: motor, l2: l2), sesion: sesion, torreMotor: torreMotor)
    }

    /// Decide cada pregunta para el `texto` (en orden). Sin conexión: todo ocurre en el dispositivo.
    public func decidir(_ texto: String, _ preguntas: [Pregunta]) -> [Respuesta] {
        preguntas.map { cascada.decidir(texto, $0) }
    }
}
