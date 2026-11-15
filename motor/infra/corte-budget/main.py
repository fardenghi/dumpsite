"""Stops every VM in the project when the budget reaches 100 % (cost without credits >= budget amount)."""
import base64
import json
import os

import functions_framework
from google.cloud import compute_v1

PROYECTO = os.environ["PROYECTO"]


@functions_framework.cloud_event
def cortar(evento):
    datos = json.loads(base64.b64decode(evento.data["message"]["data"]).decode())
    costo, tope = float(datos["costAmount"]), float(datos["budgetAmount"])
    print(f"budget: costo {costo} de {tope} {datos.get('currencyCode')}")
    if costo < tope:
        return
    cliente = compute_v1.InstancesClient()
    for zona, lista in cliente.aggregated_list(project=PROYECTO):
        for vm in lista.instances or []:
            if vm.status in ("RUNNING", "PROVISIONING", "STAGING"):
                print(f"deteniendo {vm.name} en {zona}")
                cliente.stop(project=PROYECTO, zone=zona.split("/")[-1], instance=vm.name)
