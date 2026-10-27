"""AstroTrack desktop entry point; owns its local review service."""
import sys
import tkinter as tk
from tkinter import ttk
from astro.desktop import AstroPanel


def main():
    root=tk.Tk()
    root.title('AstroTrack')
    root.geometry('900x540')
    root.minsize(780,480)
    ttk.Style(root).theme_use('clam')
    panel=AstroPanel(root)
    def close():
        panel.status.config(text='Closing AstroTrack; finishing any active file move…')
        root.update_idletasks()
        panel.closing=True
        if panel.busy:
            root.after(100,close)
            return
        panel.dispose()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    if len(sys.argv)>1:
        root.after(100,lambda:panel.open_report(sys.argv[1]))
    else:
        root.after(100,panel.activate)
    root.mainloop()


if __name__=='__main__':
    main()
