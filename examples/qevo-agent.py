import qevo
import operator
from qiskit import QuantumCircuit
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END
from load_credentials import setup_qiskit_account
from typing import Annotated, TypedDict
import json
import os
import traceback
import numpy as np
import logging

logger = logging.getLogger(qevo.__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

service = setup_qiskit_account()
backend = service.least_busy(simulator=False, operational=True) 
props = backend.properties()
cfg   = backend.configuration()

props_str="Backend: "+backend.name+"\n"
props_str+="Qubit count: "+str(backend.num_qubits)+"\n"
props_str+="Basis gates: "+json.dumps(backend.operation_names)+"\n\n"
print(props_str)

compiler = qevo.Compiler(backend)

# Definición de estado
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    approved: bool

# Configuración del Modelo:
# deepseek-r1:8b
# gpt-oss:20b
# gpt-oss:120b
llm = ChatOllama(model="gpt-oss:20b", format="json", temperature=0)

SYSTEM_INSTRUCTIONS = f"""
{props_str}
Eres 'QuantumMaster', un asistente experto en síntesis y optimización de circuitos cuánticos.
Tu objetivo es ayudar al usuario a diseñar circuitos eficientes para hardware real (IBM Backends).

Cuentas con un Compilador Cuántico Auto-Evolutivo con tres estrategias: 'baseline', 'routing', y 'heavy_opt'.

INSTRUCCIONES DE COMPORTAMIENTO:
1. Analiza la petición y genera código python Qiskit.
2. La salida DEBE SER SIEMPRE un JSON válido con este formato:
   {{"message_to_display": "explicación", "qiskit_code": "unicamente la definición del circuito en python, sin llamadas a backend, al final del código se debe retornar el circuito instanciado (este código se usara directamente en eval para obtener el circuito), debe estar en formato lambda de 1 linea."}}
3. Usa este formato exacto para qiskit_code:
(lambda qc: [qc.h(0), qc.cx(0,1), qc.measure_all()] and qc)(QuantumCircuit(12))
4. Si recibes salida del compilador, interpreta los resultados para el usuario.
"""

def input_receiver(state: AgentState):
    user_input = input("\nQuantumMaster > ")
    # Enviamos el SystemMessage solo al inicio
    return {
        "messages": [
            SystemMessage(content=SYSTEM_INSTRUCTIONS),
            HumanMessage(content=user_input)
        ]
    }

def call_model(state: AgentState):
    """El Agente analiza el contexto y genera el JSON."""
    response = llm.invoke(state['messages'])
    return {"messages": [response]}

def human_approval_step(state: AgentState):
    """El usuario decide si procede."""
    raw_content = state['messages'][-1].content
    
    try:
        data = json.loads(raw_content)
    except Exception as e:
        print(f"Error parseando JSON del modelo. Contenido: {raw_content}")
        return {"approved": False, "messages": [HumanMessage(content="Error en formato JSON. Repite la propuesta.")]}

    print(f"\n[RESPUESTA]:\n{data['message_to_display']}")
    print(f"\n[Qiskit]:\n{data['qiskit_code']}")

    choice = input("\n¿Proceder con la optimización? (si / no / corregir): ").lower()
    
    if choice == 'si':
        print('> Evaluando circuito en el Compilador Inteligente...')
        try:
            namespace = {'QuantumCircuit': QuantumCircuit, 'np': np}
            qc = eval(data['qiskit_code'], {"__builtins__": __builtins__}, namespace)
            print("[QC]:\n",qc)
            outputs = compiler.evaluate(qc)
            
            # Preparamos el feedback para el agente (el último resultado)
            debug_info = json.dumps(outputs)
            feedback_for_agent = f"Optimización completada. Resultados del compilador:\n{debug_info}\nPor favor, explica estos resultados al usuario y según la información proporcionada cual es la mejor estrategia."
            return {"approved": True, "messages": [HumanMessage(content=feedback_for_agent)]}
        except Exception as e:
            traceback.print_exc()
            return {"approved": False, "messages": [HumanMessage(content=f"Error técnico al procesar el circuito: {str(e)}")]}

    elif choice == 'corregir':
        feedback = input("¿Qué ajustes deseas?: ")
        return {"approved": False, "messages": [HumanMessage(content=f"Feedback del usuario: {feedback}")]}
    else:
        print("Proceso abortado.")
        return {"approved": True, "messages": [HumanMessage(content="Fin de la sesión.")]}

# --- Construcción del Grafo ---
workflow = StateGraph(AgentState)

workflow.add_node("input_receiver", input_receiver)
workflow.add_node("agent", call_model)
workflow.add_node("human_review", human_approval_step)

workflow.set_entry_point("input_receiver")
workflow.add_edge("input_receiver", "agent")
workflow.add_edge("agent", "human_review")

def route_after_review(state: AgentState):
    # Si el usuario dijo "si", evaluamos y volvemos al agente para que explique los resultados finales
    # Si dijo "corregir", vuelve al agente para que ajuste el circuito
    # Solo termina si el mensaje final es de cierre.
    last_msg = state['messages'][-1].content
    if "Fin de la sesión" in last_msg:
        return END
    return "agent"

workflow.add_conditional_edges("human_review", route_after_review)

app = workflow.compile()

if __name__ == "__main__":
    initial_config = {"messages": [], "approved": False}
    try:
        app.invoke(initial_config)
    except KeyboardInterrupt:
        print("\nApagando sistema...")