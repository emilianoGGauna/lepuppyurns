function toggleMenu() {
    const menu = document.querySelector(".menu");
    menu.style.display = menu.style.display === "flex" ? "none" : "flex";
}

function updateColorOptions(selectedType) {
    const colorOptions = {
        {% if 'Tipo Urna' in model['Forms'] and 'Chapa' in model['Forms']['Tipo Urna'] %}
        Chapa: {{ model['Forms']['Tipo Urna']['Chapa']['Colores'] | safe }},
        {% else %}
        Chapa: [],
        {% endif %}
        {% if 'Tipo Urna' in model['Forms'] and 'MDF' in model['Forms']['Tipo Urna'] %} 
        MDF: {{ model['Forms']['Tipo Urna']['MDF']['Colores'] | safe }} 
        {% else %}
        MDF: []
        {% endif %}
    };

    const colorSelect = document.getElementById('color');
    colorSelect.innerHTML = '';

    if (colorOptions[selectedType]) {
        colorOptions[selectedType].forEach(color => {
            const option = document.createElement('option');
            option.value = color;
            option.textContent = color;
            colorSelect.appendChild(option);
        });
    }
}