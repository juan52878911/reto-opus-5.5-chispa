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

    /// El proveedor de ORT con el que quedó L2 (`.cpu` si CoreML falló); nil sin L2 o con una sesión de otro tipo.
    public var proveedorOrt: ProveedorOrt? { (sesion as? SesionOrt)?.proveedorEfectivo }

    /// Abre el modelo en `ruta` (un fichero de verdad: el motor lo mapea en memoria).
    /// `lambdaSoporteL1`/`lambdaSoporteL2`: λ del soporte few-shot (mismo nombre y semántica que `l1_shrinkage_lambda`/`l2_shrinkage_lambda`
    /// del servidor). `lambdaSoporteL1` vale `lambdaSoporteL1PorDefecto` (4,0; medido en G.8b) si no se pasa; pasar `nil` es el apagado
    /// explícito de L1 (lo de antes del default). `lambdaSoporteL2` nil = apagado (sin default). 0 = solo ejemplos, `.infinity` = solo
    /// descripción; negativo o NaN lanza error. Sin sección SOPL1 en el fichero el default no tiene efecto.
    public static func abrir(ruta: String, tokenizador: Tokenizador? = nil, rutaTokenizador: String? = nil,
                             coreML: Bool = true, proveedorOrt: ProveedorOrt? = nil,
                             codificadorTorres: CodificadorTorre? = nil,
                             alErrorCapa: @escaping (String, Error) -> Void = Cascada.registrarErrorCapa,
                             lambdaSoporteL1: Double? = Chispa.lambdaSoporteL1PorDefecto, lambdaSoporteL2: Double? = nil) throws -> Chispa {
        guard FileManager.default.isReadableFile(atPath: ruta) else { throw ErrorChispa("no existe el modelo \(ruta)") }
        let motor = try MotorNativo.abrir(ruta: ruta, soporte: try soporteDe(lambdaSoporteL1, lambdaSoporteL2))
        // `proveedorOrt` manda; sin él, `coreML` (true por defecto) elige entre CoreML y CPU.
        let proveedor = proveedorOrt ?? (coreML ? .coreML : .cpu)
        do {
            var tok = tokenizador
            if tok == nil, let rt = rutaTokenizador {
                try motor.cargarTokenizadorE5(ruta: rt)
                tok = TokenizadorMotor(motor: motor)
            }
            return try montar(motor: motor, tokenizador: tok, onnx: {
                // nombre por hash de la sección L2 (no por tamaño) y extracción atómica: no se repite en cada arranque
                try CacheFicheros.rutaOnnxL2(motor: motor, dir: FileManager.default.temporaryDirectory, modelo: ruta)
            }, crearSesion: { try SesionOrt(rutaOnnx: $0, proveedor: proveedor) }, codificadorTorres: codificadorTorres,
                              crearSesionTorre: { try SesionTorreOrt(onnx: $0, proveedor: proveedor) },
                              alErrorCapa: alErrorCapa)
        } catch {
            motor.cerrar()
            throw error
        }
    }

    /// λ de L1 por defecto (`chispamovil.SoporteL1PorDefecto`; G.8b: massive 0,395 vs 0,266, inyecciones 0,740 vs 0,326, hatecheck 0,492 vs 0,224, JevBench 0,379 vs 0,398).
    public static let lambdaSoporteL1PorDefecto: Double = 4.0

    /// `chispamovil.SoporteApagado`: el λ negativo que apaga el encogimiento en el puente (que no tiene opcionales).
    static let lambdaApagado: Double = -1

    /// (λL1, λL2) para `AbrirConSoporte`; un λ nil es apagado (`lambdaApagado`). Siempre explícito: `Abrir` del puente ya usa 4 en L1.
    /// 0 = solo ejemplos; `.infinity` = solo descripción (ya no apaga).
    /// Un λ negativo o NaN es error (como el servidor con `l1_shrinkage_lambda < 0`): el puente usa el negativo como apagado.
    static func soporteDe(_ l1: Double?, _ l2: Double?) throws -> (Double, Double) {
        for (nombre, l) in [("lambdaSoporteL1", l1), ("lambdaSoporteL2", l2)] {
            if let l = l, l.isNaN || l < 0 { throw ErrorChispa("\(nombre) inválido (\(l)): debe ser nil (apagado) o >= 0") }
        }
        return (l1 ?? lambdaApagado, l2 ?? lambdaApagado)
    }

    /// Monta la cascada sobre cualquier `Motor` (los tests usan uno falso). `onnx` da la ruta del ONNX de L2.
    static func montar(motor: Motor, tokenizador: Tokenizador?, onnx: () throws -> String,
                       crearSesion: (String) throws -> SesionRanuras,
                       codificadorTorres: CodificadorTorre? = nil,
                       crearSesionTorre: @escaping (Data) throws -> SesionTorre = { try SesionTorreOrt(onnx: $0) },
                       alErrorCapa: @escaping (String, Error) -> Void = Cascada.registrarErrorCapa) throws -> Chispa {
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
        return Chispa(motor: motor, cascada: try Cascada.armar(motor: motor, l2: l2, alErrorCapa: alErrorCapa), sesion: sesion, torreMotor: torreMotor)
    }

    /// Decide cada pregunta para el `texto` (en orden). Sin conexión: todo ocurre en el dispositivo.
    public func decidir(_ texto: String, _ preguntas: [Pregunta]) -> [Respuesta] {
        preguntas.map { cascada.decidir(texto, $0) }
    }
}
