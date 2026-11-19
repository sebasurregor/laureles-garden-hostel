"""Traslada los registros de la tabla original del equipo (Usuario_hostal)
al nuevo modelo huespedes + estancias, SIN borrar ni modificar la tabla original.

Equivalencia de campos (tabla original -> nuevo modelo):
    Nombres              -> huespedes.nombres
    Apellidos            -> huespedes.apellidos
    Tipo_Documento       -> huespedes.tipo_documento (texto -> código CC, CE, PA...)
    Numero_Documento     -> huespedes.numero_documento_cifrado (+ documento_hash)
    Fecha_Arrendamiento  -> estancias.fecha_ingreso
    Lugar_Provenida      -> estancias.procedencia
    Lugar_Partida        -> estancias.destino
    fecha_Checkout       -> estancias.checkout_en (y fecha_salida_prevista)
"""
from psycopg import sql

from .cifrado import cifrar, huella_documento, texto_para_buscar, ultimos_digitos

EQUIVALENCIA_TIPOS = {
    "cedula de ciudadania": "CC",
    "cedula de extranjeria": "CE",
    "pasaporte": "PA",
    "tarjeta de identidad": "TI",
}
NOTA_MIGRADO = "Registro migrado del formulario del Sprint 1."


def buscar_tabla_original(conexion):
    """Busca la tabla original tal como exista: con comillas (pgAdmin) o en minúsculas."""
    fila = conexion.execute(
        """SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND lower(table_name) = 'usuario_hostal'
            ORDER BY table_name LIMIT 1"""
    ).fetchone()
    if not fila:
        return None, {}
    nombre = fila["table_name"]
    columnas = {
        c["column_name"].lower(): c["column_name"]
        for c in conexion.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name = %s",
            (nombre,),
        ).fetchall()
    }
    return nombre, columnas


def migrar(conexion):
    """Devuelve un resumen {'leidos', 'huespedes_nuevos', 'estancias_nuevas', 'omitidos'}."""
    tabla, col = buscar_tabla_original(conexion)
    resumen = {"tabla": tabla, "leidos": 0, "huespedes_nuevos": 0, "estancias_nuevas": 0, "omitidos": 0}
    if not tabla:
        return resumen

    def c(nombre):  # identificador real de la columna, con comillas si hace falta
        return sql.Identifier(col[nombre.lower()])

    consulta = sql.SQL(
        "SELECT {id}, {n}, {a}, {t}, {d}, {f}, {p}, {s}, {co} FROM {tabla} ORDER BY {id}"
    ).format(
        id=c("Id_Usuario_hostal"), n=c("Nombres"), a=c("Apellidos"), t=c("Tipo_Documento"),
        d=c("Numero_Documento"), f=c("Fecha_Arrendamiento"), p=c("Lugar_Provenida"),
        s=c("Lugar_Partida"), co=c("fecha_Checkout"), tabla=sql.Identifier(tabla),
    )
    filas = conexion.execute(consulta).fetchall()

    with conexion.transaction():  # todo o nada
        for fila in filas:
            v = list(fila.values())
            id_original, nombres, apellidos, tipo_texto, documento, fecha_ingreso, procedencia, destino, checkout = v
            resumen["leidos"] += 1
            # No migrar dos veces el mismo registro.
            ya = conexion.execute(
                "SELECT 1 FROM estancias WHERE observaciones = %s",
                (f"{NOTA_MIGRADO} Id original {id_original}.",),
            ).fetchone()
            if ya:
                resumen["omitidos"] += 1
                continue
            tipo = EQUIVALENCIA_TIPOS.get(texto_para_buscar(tipo_texto), "OTRO")
            huella = huella_documento(documento)
            huesped = conexion.execute(
                "SELECT id FROM huespedes WHERE tipo_documento = %s AND documento_hash = %s",
                (tipo, huella),
            ).fetchone()
            if not huesped:
                huesped = conexion.execute(
                    """INSERT INTO huespedes (nombres, apellidos, nombre_busqueda, tipo_documento,
                           numero_documento_cifrado, documento_hash, documento_ultimos, nacionalidad)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, 'Sin dato') RETURNING id""",
                    (nombres.strip(), apellidos.strip(), texto_para_buscar(f"{nombres} {apellidos}"),
                     tipo, cifrar(documento.strip()), huella, ultimos_digitos(documento)),
                ).fetchone()
                resumen["huespedes_nuevos"] += 1
            salida = checkout.date() if checkout else fecha_ingreso
            if salida < fecha_ingreso:
                salida = fecha_ingreso
            conexion.execute(
                """INSERT INTO estancias (huesped_id, fecha_ingreso, fecha_salida_prevista,
                       checkout_en, procedencia, destino, estado, observaciones)
                   VALUES (%s, %s, %s, %s AT TIME ZONE 'America/Bogota', %s, %s, 'finalizada', %s)""",
                (huesped["id"], fecha_ingreso, salida, checkout, procedencia.strip(), destino.strip(),
                 f"{NOTA_MIGRADO} Id original {id_original}."),
            )
            resumen["estancias_nuevas"] += 1
    return resumen
