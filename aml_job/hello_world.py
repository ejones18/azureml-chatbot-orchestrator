"""Hello World sample script for Azure ML.

This is a minimal sample script used as a proof-of-concept to verify
end-to-end job submission. It is registered as an AML component
(see hello_world_component.yaml) and submitted as a command job by
the Azure Function.

Replace this with your actual training or processing logic.
"""

import time

print("Hello World from Azure ML!")
print("Job is running successfully...")
time.sleep(5)
print("Job complete!")
