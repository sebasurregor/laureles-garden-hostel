# Reporte de optimización de rendimiento (HU-10)

- **Fecha:** 2026-11-19 20:21
- **Volumen probado:** 3073 huéspedes demo
- **Iteraciones por vista:** 20
- **Usuarios simultáneos (concurrencia):** 8

## 1. Comparativa por vista (tiempos en milisegundos)

| Vista | Antes (prom) | Después (prom) | Mejora | Después (p95) | Cumple < 2000 ms |
|---|---:|---:|---:|---:|:---:|
| En casa | 47.4 ms | 5.6 ms | +88.3% | 11.9 ms | Sí |
| Llegadas pendientes | 56.1 ms | 3.5 ms | +93.8% | 4.8 ms | Sí |
| Búsqueda por nombre | 48.2 ms | 4.4 ms | +90.9% | 6.7 ms | Sí |
| Búsqueda por documento | 77.5 ms | 1.6 ms | +97.9% | 2.8 ms | Sí |
| Historial | 76.1 ms | 3.4 ms | +95.6% | 4.8 ms | Sí |
| Ficha de huésped | 57.1 ms | 2.0 ms | +96.5% | 2.9 ms | Sí |

## 2. Prueba bajo concurrencia simultánea

| Escenario | Peticiones | Promedio | p95 | Máximo |
|---|---:|---:|---:|---:|
| Antes (sin pool ni índices 003) | 48 | 68.3 ms | 143.1 ms | 150.5 ms |
| Después (pool + índices 003) | 48 | 21.8 ms | 55.2 ms | 58.4 ms |

**Reducción promedio bajo concurrencia:** +68.1%
