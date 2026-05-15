from dotenv import load_dotenv
from qiskit_ibm_runtime import QiskitRuntimeService
import os
def setup_qiskit_account():
    # Cargar variables desde el archivo .env
    load_dotenv()
    try:
        service = QiskitRuntimeService(channel="ibm_quantum_platform")
    except Exception:
        try:
            token = os.getenv("IBM_QUANTUM_TOKEN")
            instance = os.getenv("IBM_QUANTUM_INSTANCE")
            if not token:
                raise ValueError("Error: No se encontró IBM_QUANTUM_TOKEN en el archivo .env")
            QiskitRuntimeService.save_account(
                token=token,
                instance=instance,
                channel="ibm_quantum_platform",
                overwrite=True
            )
            service = QiskitRuntimeService(channel="ibm_quantum_platform")
        except Exception as e:
            return None
    return service