-- =====================================================================
-- Laureles Garden Hostel · Migración 003 (Entrega 3 · HU-10)
-- Índices para optimizar búsquedas por nombre, listado en casa,
-- llegadas pendientes, historial filtrado y ficha de huéspedes.
-- =====================================================================

CREATE INDEX IF NOT EXISTS idx_huespedes_nombre_busqueda_prefix
    ON huespedes (nombre_busqueda text_pattern_ops);

CREATE INDEX IF NOT EXISTS idx_huespedes_apellidos_nombres
    ON huespedes (apellidos, nombres);

-- Extensión pg_trgm + índice GIN para búsquedas parciales LIKE '%texto%'
-- Si el servidor gestionado no otorga permisos para CREATE EXTENSION, se omite sin fallar.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE INDEX IF NOT EXISTS idx_huespedes_nombre_busqueda_trgm
        ON huespedes USING gin (nombre_busqueda gin_trgm_ops);
EXCEPTION
    WHEN insufficient_privilege OR undefined_file OR feature_not_supported THEN
        RAISE NOTICE 'pg_trgm no disponible en este entorno; se usará el índice B-tree estándar.';
END $$;

CREATE INDEX IF NOT EXISTS idx_estancias_en_casa_salida
    ON estancias (fecha_salida_prevista, huesped_id)
    WHERE estado = 'en_casa';

CREATE INDEX IF NOT EXISTS idx_estancias_pendientes_ingreso
    ON estancias (fecha_ingreso, huesped_id)
    WHERE estado = 'pendiente';

CREATE INDEX IF NOT EXISTS idx_estancias_fecha_id_desc
    ON estancias (fecha_ingreso DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_estancias_estado_fecha_id
    ON estancias (estado, fecha_ingreso DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_estancias_huesped_fecha
    ON estancias (huesped_id, fecha_ingreso DESC, id DESC);
