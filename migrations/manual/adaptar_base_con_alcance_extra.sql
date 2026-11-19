-- =====================================================================
-- SOLO para una base creada con la versión anterior (rama alcance-extra),
-- que tiene las tablas habitaciones, pagos, cargos_adicionales y auditoria.
--
-- NO se ejecuta automáticamente. Ejecutar a mano (pgAdmin > Query Tool)
-- únicamente después de que la clienta/gerencia lo apruebe y de hacer
-- un respaldo con scripts\backup.ps1.
--
-- Qué hace (no borra tablas ni datos):
--   1. Agrega estancias.habitacion (texto) y copia el código de la habitación.
--   2. Quita la regla que exigía habitacion_id para estar "en casa".
--   3. Desactiva (sin borrarlo) el control de capacidad por habitación, que
--      dependía de la tabla habitaciones. Se reactiva con:
--      ALTER TABLE estancias ENABLE TRIGGER trg_estancias_capacidad;
-- Las tablas habitaciones, pagos, cargos_adicionales y auditoria quedan
-- intactas, sin uso, por si la clienta solicita después ese alcance.
-- =====================================================================
BEGIN;

ALTER TABLE estancias ADD COLUMN IF NOT EXISTS habitacion varchar(20);

UPDATE estancias e
   SET habitacion = h.codigo
  FROM habitaciones h
 WHERE h.id = e.habitacion_id AND e.habitacion IS NULL;

DO $$
DECLARE
    regla text;
BEGIN
    FOR regla IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'estancias'::regclass AND contype = 'c'
           AND pg_get_constraintdef(oid) LIKE '%en_casa%habitacion_id%'
    LOOP
        EXECUTE format('ALTER TABLE estancias DROP CONSTRAINT %I', regla);
    END LOOP;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_estancias_capacidad') THEN
        ALTER TABLE estancias DISABLE TRIGGER trg_estancias_capacidad;
    END IF;
END $$;

COMMIT;
