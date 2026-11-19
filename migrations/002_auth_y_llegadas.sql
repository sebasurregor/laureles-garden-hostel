-- =====================================================================
-- Laureles Garden Hostel · Migración 002 (Entrega 3)
-- HU-07: Tabla de usuarios autorizados para el panel de recepción.
-- HU-06: Estado 'pendiente' (pendiente de llegada) en estancias.
-- HU-09: Tabla de registro de despliegues y versiones publicadas.
-- Compatible con datos existentes: no elimina ni sobrescribe registros.
-- =====================================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id              serial PRIMARY KEY,
    usuario         varchar(40)  NOT NULL UNIQUE,
    nombre_completo varchar(120) NOT NULL,
    rol             varchar(20)  NOT NULL DEFAULT 'recepcion'
                    CHECK (rol IN ('admin', 'recepcion')),
    password_hash   text         NOT NULL,
    activo          boolean      NOT NULL DEFAULT true,
    creado_en       timestamptz  NOT NULL DEFAULT now(),
    ultimo_acceso   timestamptz
);

ALTER TABLE estancias ADD COLUMN IF NOT EXISTS actualizado_en timestamptz;

DO $$
DECLARE
    regla text;
BEGIN
    FOR regla IN
        SELECT conname
          FROM pg_constraint
         WHERE conrelid = 'estancias'::regclass
           AND contype = 'c'
           AND pg_get_constraintdef(oid) LIKE '%en_casa%'
           AND pg_get_constraintdef(oid) LIKE '%finalizada%'
    LOOP
        EXECUTE format('ALTER TABLE estancias DROP CONSTRAINT %I', regla);
    END LOOP;
END $$;

ALTER TABLE estancias
    ADD CONSTRAINT chk_estancias_estado
    CHECK (estado IN ('pendiente', 'en_casa', 'finalizada'));

CREATE TABLE IF NOT EXISTS despliegues (
    id             serial PRIMARY KEY,
    version        varchar(40)  NOT NULL,
    entorno        varchar(30)  NOT NULL DEFAULT 'produccion',
    resultado      varchar(20)  NOT NULL
                   CHECK (resultado IN ('exitoso', 'fallido', 'revertido')),
    notas          varchar(500),
    desplegado_por varchar(80),
    desplegado_en  timestamptz  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_despliegues_fecha ON despliegues (desplegado_en DESC);
