import tkinter as tk
import tkinter.ttk as ttk
from tkinter import filedialog, messagebox
import zipfile
import os
import shutil


import subprocess

def _pick_folder(title="Select folder"):
    try:
        result = subprocess.run(
            ["zenity", "--file-selection", "--directory", f"--title={title}"],
            capture_output=True, text=True
        )
        return result.stdout.strip() or None
    except FileNotFoundError:
        pass
    try:
        result = subprocess.run(
            ["kdialog", "--getexistingdirectory", os.path.expanduser("~"), "--title", title],
            capture_output=True, text=True
        )
        return result.stdout.strip() or None
    except FileNotFoundError:
        pass
    return filedialog.askdirectory(title=title)  # fallback

def _pick_files(title="Select files"):
    try:
        result = subprocess.run(
            ["zenity", "--file-selection", "--multiple", "--file-filter=Zip files | *.zip", f"--title={title}"],
            capture_output=True, text=True
        )
        out = result.stdout.strip()
        return out.split("|") if out else []
    except FileNotFoundError:
        pass
    try:
        result = subprocess.run(
            ["kdialog", "--getopenfilename", os.path.expanduser("~"), "*.zip", "--title", title],
            capture_output=True, text=True
        )
        out = result.stdout.strip()
        return out.split("\n") if out else []
    except FileNotFoundError:
        pass
    paths = filedialog.askopenfilenames(title=title, filetypes=[("Zip files", "*.zip")])
    return list(paths)


class ReorderableApp:
    def __init__(self, root):
        self.root = root
        self.root.title("yagml")

        self.mods = []
        self.target_folder = None


        self.folder_label = tk.Label(root, text="No folder loaded", anchor="w", fg="gray")
        self.folder_label.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(8, 0))


        main_frame = tk.Frame(root)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.listbox = tk.Listbox(main_frame, selectmode=tk.SINGLE, width=40, height=12)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))

        self.up_btn = tk.Button(btn_frame, text="Move Up", command=self.move_up, width=12)
        self.up_btn.pack(fill=tk.X, pady=2)

        self.down_btn = tk.Button(btn_frame, text="Move Down", command=self.move_down, width=12)
        self.down_btn.pack(fill=tk.X, pady=2)

        self.delete_btn = tk.Button(btn_frame, text="Remove Mod", command=self.delete, width=12)
        self.delete_btn.pack(fill=tk.X, pady=2)

        # === Priority note ===
        note = tk.Label(root, text="higher = higher priority", fg="gray", font=("TkDefaultFont", 8))
        note.pack(side=tk.TOP, anchor="w", padx=10)

        # === Bottom buttons ===
        bottom_frame = tk.Frame(root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=8)

        self.load_btn = tk.Button(bottom_frame, text="Load Folder", command=self.load_folder, width=12)
        self.load_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.add_btn = tk.Button(bottom_frame, text="Add Mod", command=self.add_mod, width=12)
        self.add_btn.pack(side=tk.LEFT, padx=4)

        self.apply_btn = tk.Button(bottom_frame, text="Apply Mods", command=self.apply_mods, width=12)
        self.apply_btn.pack(side=tk.RIGHT)



    def load_folder(self):

        folder = _pick_folder("Select target folder")
        if folder:
            self.target_folder = folder
            self.folder_label.config(text=f"Target: {folder}", fg="black")

    def add_mod(self):
        paths = _pick_files("Select mod zip(s)")
        for path in paths:
            name = os.path.basename(path)
            # Avoid duplicates
            if any(p == path for _, p in self.mods):
                continue
            self.mods.append((name, path))
            self.listbox.insert(tk.END, name)

# helper functions and stuff

    def _swap(self, i, j):
        self.mods[i], self.mods[j] = self.mods[j], self.mods[i]
        self._refresh_listbox(j)

    def _refresh_listbox(self, select_index=None):
        self.listbox.delete(0, tk.END)
        for name, _ in self.mods:
            self.listbox.insert(tk.END, name)
        if select_index is not None:
            self.listbox.selection_set(select_index)

    def move_up(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        self._swap(i, i - 1)

    def move_down(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] == len(self.mods) - 1:
            return
        i = sel[0]
        self._swap(i, i + 1)

    def delete(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        i = sel[0]
        self.mods.pop(i)
        self.listbox.delete(i)

    def apply_mods(self):
        if not self.target_folder:
            messagebox.showwarning("No folder", "Please load a target folder first.")
            return
        if not self.mods:
            messagebox.showwarning("No mods", "Please add at least one mod.")
            return

        # Output folder sits next to the target folder, named <folder>_modded
        parent = os.path.dirname(self.target_folder)
        base = os.path.basename(self.target_folder)
        output_folder = os.path.join(parent, base + "_modded")

        # Start fresh: copy original files
        if os.path.exists(output_folder):
            shutil.rmtree(output_folder)
        shutil.copytree(self.target_folder, output_folder)

        # Apply mods in reverse order, Lower-priority mods are written first, higher-priority mods overwrite them.
        conflict_log = []  # (file, winning_mod)


        written_by = {}

        for name, path in reversed(self.mods):
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    members = zf.infolist()

                    # Check if the zip has a single top-level folder matching the zip name
                    zip_stem = os.path.splitext(os.path.basename(path))[0]
                    top_level = set()
                    for m in members:
                        top = m.filename.split("/")[0]
                        top_level.add(top)

                    strip_prefix = None
                    if len(top_level) == 1:
                        sole = next(iter(top_level))
                        if sole == zip_stem:
                            strip_prefix = sole + "/"

                    for member in members:
                        if member.is_dir():
                            continue
                        rel = member.filename
                        if strip_prefix:
                            if not rel.startswith(strip_prefix):
                                continue
                            rel = rel[len(strip_prefix):]  # strip the wrapper folder
                        dest = os.path.join(output_folder, rel)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with zf.open(member) as src, open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        if rel in written_by:
                            conflict_log.append((rel, name))
                        written_by[rel] = name
            except zipfile.BadZipFile:
                messagebox.showerror("Bad zip", f"Could not read '{name}' — skipping.")

        # Build summary
        msg = f"Mods applied!\nOutput folder:\n{output_folder}"
        if conflict_log:
            # Show only conflicts where higher-priority mod won (written last)
            lines = "\n".join(f"  {f}  ←  {m}" for f, m in conflict_log[-10:])
            if len(conflict_log) > 10:
                lines += f"\n  … and {len(conflict_log) - 10} more"
            msg += f"\n\n{len(conflict_log)} conflict(s) resolved (higher-priority mod shown):\n{lines}"

        messagebox.showinfo("Done", msg)


if __name__ == "__main__":
    root = tk.Tk()
    app = ReorderableApp(root)
    root.mainloop()
