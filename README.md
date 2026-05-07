
<div align="center">

# 🏎️  Estratégia de Pit Stop: Simulador de F1
### *Sistema Estocástico para Otimização de Estratégias de Pit Stop na Fórmula 1*

Simulador analítico desenvolvido como Trabalho de Conclusão de Curso em **Sistemas de Informação (UGB/FERP)**, utilizando **Ciência de Dados**, **Simulação Estocástica** e **Telemetria Real** para modelar, prever e otimizar estratégias de corrida.

<br>

<a href="https://simulador-pit-stop.streamlit.app" target="_blank">
  <img src="https://img.shields.io/badge/▶%20ACESSAR%20SIMULADOR%20ONLINE-e10600?style=for-the-badge&logo=formula1&logoColor=white" alt="Acessar Simulador Online" />
</a>

<a href="https://github.com/Simulador-F1-BR/simulador-pit-stop" target="_blank">
  <img src="https://img.shields.io/badge/📂%20VER%20CÓDIGO-171515?style=for-the-badge&logo=github&logoColor=white" alt="Repositório" />
</a>

<br><br>

<img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.9+">
<img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=flat-square&logo=streamlit&logoColor=white" alt="Streamlit">
<img src="https://img.shields.io/badge/FastF1-Telemetria%20Oficial-red?style=flat-square" alt="FastF1">


</div>

<br>

---

## 🌟 Visão Geral

A **Estratégia de Pit Stop: Simulador de F1** é uma plataforma interativa de simulação computacional desenvolvida para analisar e prever estratégias de pit stop em corridas de Fórmula 1.

O sistema integra **dados reais de telemetria da FIA**, **modelagem matemática** e **simulação probabilística** para reproduzir cenários de corrida com alto grau de realismo, permitindo tanto:

- **Backtesting** → análise e validação de corridas históricas;
- **Modo Preditivo** → projeções estratégicas baseadas em dados de treinos livres;
- **Comparação de Estratégias** → avaliação de múltiplas janelas de parada;
- **Análise Estocástica** → incorporação de incertezas reais da corrida.

---

## ✨ Principais Funcionalidades

### 📡 Integração com Telemetria Real
Consumo de dados oficiais via **FastF1**, incluindo tempos de volta, stints, compostos de pneus e condições de pista.

### 🎲 Motor Estocástico (Monte Carlo)
Execução de milhares de simulações probabilísticas para calcular:

- intervalo de confiança;
- melhor janela de pit stop;
- impacto de eventos aleatórios;
- robustez da estratégia.

### 📈 Modelagem Analítica
Uso de **Regressão Linear** para:

- estimativa de degradação dos pneus;
- cálculo de ritmo médio;
- previsão de performance por stint.

### 🌦️ Variáveis Dinâmicas
Configuração personalizada de:

- clima;
- nebulosidade;
- chance de chuva;
- tráfego;
- desgaste inicial dos compostos;
- penalidades operacionais.

### 📊 Visualização Interativa
Dashboard com:

- gráficos comparativos;
- análise de stint;
- projeções estratégicas;
- indicadores estatísticos;
- relatórios automáticos.

---

## 🧠 Metodologia Técnica

O sistema opera em três camadas principais:

### 1) Ingestão de Dados
O backend consome telemetria histórica e dados oficiais do GP selecionado.

### 2) Motor Analítico
São aplicados dois pilares matemáticos:

- **Regressão Linear** → modelagem da curva de desgaste e pace;
- **Método de Monte Carlo** → simulação de milhares de cenários alternativos.

Isso permite incorporar variáveis imprevisíveis como:

- erro humano no pit stop;
- alterações climáticas;
- tráfego;
- degradação variável;
- oscilações de ritmo.

### 3) Visualização
O frontend renderiza:

- estratégia ideal;
- janela ótima de parada;
- comparação entre pilotos;
- projeção estatística dos resultados.

---

## ✅ Casos de Validação

O simulador foi validado com cenários distintos:

- **GP do Brasil 2024** → comportamento caótico e múltiplas interrupções;
- **GP de Mônaco 2025** → convergência com estratégia vencedora real;
- **GP de Miami 2026** → projeção preditiva baseada em dados de TL1.

Esses cenários demonstraram robustez analítica, capacidade de generalização e aplicação prática do modelo.

---

## 🛠️ Tecnologias Utilizadas

| Tecnologia | Finalidade |
|:---|:---|
| **Python** | Linguagem principal |
| **Streamlit** | Interface interativa |
| **FastF1** | Extração de telemetria FIA |
| **Pandas / NumPy** | Manipulação e modelagem de dados |
| **Matplotlib / Plotly** | Visualização analítica |

---

## 🚀 Como Executar Localmente

### Pré-requisitos
- Python **3.9+**

### 1) Clone o repositório
```bash
git clone https://github.com/Simulador-F1-BR/simulador-pit-stop.git
cd simulador-pit-stop
````

### 2) Instale as dependências

```bash
pip install -r requirements.txt
```

### 3) Execute o sistema

```bash
streamlit run app.py
```

---

## 📂 Estrutura do Projeto

```text
simulador-pit-stop/
│── app.py
│── config.py
│── data_loader.py
│── montecarlo.py
│── analytics.py
│── requirements.txt
└── assets/
```

### Descrição dos módulos

* **app.py** → Interface principal do sistema
* **config.py** → Variáveis globais e configurações
* **data_loader.py** → Coleta e tratamento da telemetria
* **montecarlo.py** → Núcleo estocástico da simulação
* **analytics.py** → Processamento matemático e regressão

---

## 👥 Equipe de Desenvolvimento

**Beatriz Guimarães Furtado**

GitHub: https://github.com/beatrizfurtado03

**Rayanne Vitória Silva Marciano**

GitHub: https://github.com/rayannevits 

**Orientador:** Prof. Anderson Evandro Simeão da Silva

**Instituição:** Centro Universitário Geraldo Di Biase — UGB/FERP


## 📜 Uso e Direitos Autorais

Este projeto foi desenvolvido como Trabalho de Conclusão de Curso (TCC) em Sistemas de Informação — UGB/FERP.

O código-fonte está disponibilizado publicamente para fins de **consulta, estudo e demonstração técnica**.

Não é autorizada a **reprodução, redistribuição, modificação ou utilização comercial** deste material sem autorização prévia dos autores.

© Beatriz Guimarães Furtado & Rayanne Vitória Silva Marciano


---
<div align="center">

### 🏁 Homenagem ao legado de Ayrton Senna

 *"O medo me fascina. Ele é o aviso de que você está no limite."*  
 — **Ayrton Senna**

</div>



