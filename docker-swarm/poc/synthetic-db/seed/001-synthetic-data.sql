-- Datos sintéticos, nunca copia de datos reales — docs/31-docker-swarm.md, Fase 0.
CREATE TABLE poc_rows (
    id SERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO poc_rows (label)
SELECT 'fila-sintetica-' || g
FROM generate_series(1, 20) AS g;
