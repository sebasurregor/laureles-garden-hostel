// JavaScript mínimo de la recepción. La aplicación funciona aunque este archivo no cargue:
// aquí solo hay ayudas (aviso de huésped que regresa y validación de fechas).
// Todo pedido "fetch" que envía datos lleva el token CSRF en la cabecera X-CSRFToken.
(function () {
    'use strict';

    const tokenCSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

    async function enviarJSON(url, datos) {
        const respuesta = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': tokenCSRF },
            credentials: 'same-origin',
            body: JSON.stringify(datos)
        });
        if (!respuesta.ok) throw new Error('Respuesta ' + respuesta.status);
        return respuesta.json();
    }

    // Confirmación antes de acciones importantes (botones con data-confirmar).
    document.addEventListener('click', (evento) => {
        const boton = evento.target.closest('[data-confirmar]');
        if (boton && !window.confirm(boton.dataset.confirmar)) evento.preventDefault();
    });

    // Evita registros dobles: desactiva el botón al enviar el formulario.
    document.addEventListener('submit', (evento) => {
        const boton = evento.target.querySelector('button[type="submit"]');
        if (boton && !evento.defaultPrevented) {
            setTimeout(() => { boton.disabled = true; }, 0);
            setTimeout(() => { boton.disabled = false; }, 8000);
        }
    });

    // Registro: al escribir el documento, avisa si el huésped ya vino antes (HU-01).
    const formRegistro = document.getElementById('form-registro');
    if (formRegistro) {
        const tipo = document.getElementById('tipo_documento');
        const numero = document.getElementById('numero_documento');
        const aviso = document.getElementById('aviso-documento');
        const fechaIngreso = document.getElementById('fecha_ingreso');
        const fechaSalida = document.getElementById('fecha_salida_prevista');

        async function verificar() {
            if (!tipo.value || numero.value.trim().length < 3) return;
            try {
                const r = await enviarJSON(formRegistro.dataset.verificarUrl, { tipo: tipo.value, numero: numero.value });
                if (!r.existe) { aviso.classList.add('oculto'); return; }
                aviso.textContent = '';
                const texto = document.createElement('span');
                texto.textContent = r.en_casa
                    ? r.nombre + ' ya figura EN CASA. Revisa su estancia actual. '
                    : 'Huésped que regresa: ' + r.nombre + ' (' + r.estancias + ' estancia(s)). Se creará una nueva estancia sin duplicar sus datos. ';
                const enlace = document.createElement('a');
                enlace.href = r.url_ficha;
                enlace.textContent = 'Ver ficha';
                aviso.append(texto, enlace);
                aviso.className = 'mensaje aviso-huesped ' + (r.en_casa ? 'error' : 'info');
            } catch (e) {
                aviso.classList.add('oculto');
            }
        }
        numero.addEventListener('change', verificar);
        tipo.addEventListener('change', verificar);

        // Validación en el navegador: la salida no puede ser anterior al ingreso.
        function revisarFechas() {
            const mal = fechaIngreso.value && fechaSalida.value && fechaSalida.value < fechaIngreso.value;
            fechaSalida.setCustomValidity(mal ? 'La salida no puede ser anterior al ingreso.' : '');
        }
        fechaIngreso.addEventListener('change', revisarFechas);
        fechaSalida.addEventListener('change', revisarFechas);

        formRegistro.addEventListener('submit', (evento) => {
            revisarFechas();
            if (!formRegistro.checkValidity()) {
                evento.preventDefault();
                formRegistro.reportValidity();
                document.getElementById('estado-formulario').textContent = 'Revisa los campos marcados.';
            }
        });
    }
})();
