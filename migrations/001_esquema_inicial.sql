-- =====================================================================
-- Laureles Garden Hostel · Esquema del Sprint 1 (HU-01 a HU-04)
-- Todos los identificadores en snake_case y minúsculas, SIN comillas,
-- para evitar el error "relation ... does not exist" (ver README).
-- Este archivo lo ejecuta: flask --app app init-db
-- =====================================================================

-- Huésped: UNA fila por persona (único por tipo + documento).
CREATE TABLE huespedes (
    id                        serial PRIMARY KEY,
    nombres                   varchar(250) NOT NULL,
    apellidos                 varchar(250) NOT NULL,
    nombre_busqueda           text         NOT NULL,  -- nombres + apellidos sin tildes, en minúsculas
    tipo_documento            varchar(10)  NOT NULL
                              CHECK (tipo_documento IN ('CC', 'CE', 'PA', 'TI', 'PPT', 'OTRO')),
    numero_documento_cifrado  text         NOT NULL,  -- Fernet
    documento_hash            char(64)     NOT NULL,  -- HMAC-SHA256, para buscar sin descifrar
    documento_ultimos         varchar(4)   NOT NULL,  -- solo para mostrar "•••• 4821"
    nacionalidad              varchar(60)  NOT NULL,
    telefono_cifrado          text,                   -- Fernet
    correo_cifrado            text,                   -- Fernet
    fecha_nacimiento          date,
    acepta_tratamiento_datos  boolean      NOT NULL DEFAULT false,
    fecha_aceptacion_datos    timestamptz,
    es_demo                   boolean      NOT NULL DEFAULT false,
    creado_en                 timestamptz  NOT NULL DEFAULT now(),
    actualizado_en            timestamptz,
    UNIQUE (tipo_documento, documento_hash),
    CHECK (NOT acepta_tratamiento_datos OR fecha_aceptacion_datos IS NOT NULL)
);
CREATE INDEX idx_huespedes_documento_hash ON huespedes (documento_hash);

-- Estancia: cada visita de un huésped (un huésped puede tener muchas; HU-04).
CREATE TABLE estancias (
    id                     serial PRIMARY KEY,
    huesped_id             integer      NOT NULL REFERENCES huespedes (id),
    habitacion             varchar(20),                 -- texto libre y opcional, ej. "101" o "Dorm 2"
    canal                  varchar(20)
                           CHECK (canal IN ('Booking', 'Airbnb', 'Hostelworld', 'Google', 'Directo', 'Sin reserva')),
    fecha_ingreso          date         NOT NULL,
    fecha_salida_prevista  date         NOT NULL,
    checkin_en             timestamptz,                 -- hora en que se registró la llegada
    checkout_en            timestamptz,                 -- hora real de salida
    procedencia            varchar(250) NOT NULL,
    destino                varchar(250) NOT NULL,
    estado                 varchar(20)  NOT NULL DEFAULT 'en_casa'
                           CHECK (estado IN ('en_casa', 'finalizada')),
    observaciones          varchar(500),
    es_demo                boolean      NOT NULL DEFAULT false,
    creado_en              timestamptz  NOT NULL DEFAULT now(),
    CHECK (fecha_salida_prevista >= fecha_ingreso),
    CHECK (estado <> 'en_casa' OR checkin_en IS NOT NULL),
    CHECK (checkout_en IS NULL OR checkin_en IS NULL OR checkout_en >= checkin_en)
);
CREATE INDEX idx_estancias_huesped ON estancias (huesped_id);
CREATE INDEX idx_estancias_estado ON estancias (estado);
CREATE INDEX idx_estancias_fecha_ingreso ON estancias (fecha_ingreso);
-- Un huésped no puede estar "en casa" dos veces al mismo tiempo.
CREATE UNIQUE INDEX uq_estancias_un_en_casa_por_huesped ON estancias (huesped_id) WHERE estado = 'en_casa';
