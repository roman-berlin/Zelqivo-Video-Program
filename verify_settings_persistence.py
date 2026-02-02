
from PyQt6.QtCore import QSettings, QCoreApplication
import sys

def verify_persistence():
    with open("verification_result.txt", "w") as f:
        f.write("Starting...\n")
        try:
            app = QCoreApplication(sys.argv)
            app.setApplicationName("Zelqivo")
            app.setOrganizationName("Zelqivo")

            # 1. Clean verify
            s1 = QSettings("Zelqivo", "Zelqivo")
            s1.clear()
            s1.sync()
            f.write("Cleared settings.\n")

            # 2. Set Value
            s1.setValue("appearance/theme", "dark")
            s1.setValue("magic/sync/enabled", True)
            s1.sync()
            f.write("Saved values.\n")
            
            # 3. Simulate App Restart (New Instance)
            s2 = QSettings("Zelqivo", "Zelqivo")
            theme = s2.value("appearance/theme", "light", type=str)
            sync_enabled = s2.value("magic/sync/enabled", False, type=bool)
            
            f.write(f"Loaded: theme='{theme}', sync={sync_enabled}\n")

            if theme == "dark" and sync_enabled is True:
                f.write("SUCCESS\n")
            else:
                f.write(f"FAILURE: theme={theme}, sync={sync_enabled}\n")
        except Exception as e:
            f.write(f"CRASH: {e}\n")

if __name__ == "__main__":
    verify_persistence()
