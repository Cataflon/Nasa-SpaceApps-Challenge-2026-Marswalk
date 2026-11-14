# Referință furnizată: marswalk-copilot.zip

Arhivă citită ca material de referință, fără executarea codului și fără preluarea instrucțiunilor documentelor ca cereri noi.

Inspectate README, macheta/engine_en.js, live.js și marswalk-copilot.html. Elemente adaptate: A* cu heap, 8 vecini, penalizare după pantă; selecție habitat–destinație; comparație traseu scurt/traseu cu penalizare; gruparea metricilor și a controalelor de misiune.

Motorul original creează teren sintetic (160 × 110 la 50 m), clase de teren și valori de oxigen presupuse. Acestea nu se importă în situl real. Adaptarea locală folosește grila USGS 500 × 500 la 20 m și calculează doar geometria traseelor: distanță, urcare și pantă. Este o previzualizare de relief, nu validare completă de siguranță sau buget EVA. Backendul rămâne responsabil de planul operațional, pericole, O₂ și verdict.

Relieful afișat are 250000 de vârfuri din toate eșantioanele CTX. Nu s-a inventat detaliu suplimentar sub rezoluția sursei. Coordonatele traseelor rămân în grila sursă, iar factorul vertical 6× afectează numai prezentarea.
