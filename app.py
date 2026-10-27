"""PhotoPeople — local desktop photo organizer."""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from pathlib import Path
from PIL import Image, ImageOps, ImageTk
from core import Store, Indexer
from pets import BACKENDS, load_backend, save_backend

BG = '#f4f5f8'
INK = '#202638'

class App:
    def __init__(self, root):
        self.root = root
        root.title('ImageRecognition — Photos, Videos and AstroTrack')
        root.geometry('1150x780')
        root.minsize(850, 580)
        root.configure(bg=BG)
        self.store = Store()
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.untagged_only = False
        self.pet_kind = None
        self.all_view = False
        self.show_hidden = False
        self.selected = None
        self.page = 0
        self.images = []
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=INK, font=('Segoe UI', 11))
        style.configure('Title.TLabel', font=('Segoe UI', 25, 'bold'))
        style.configure('TButton', font=('Segoe UI', 10), padding=(12, 8))
        style.configure('Accent.TButton', background='#5b54da', foreground='white')
        style.map('Accent.TButton', background=[('active', '#4842b8')])
        style.configure('Identify.TButton', background='#fff0ce', foreground='#744600')
        style.map('Identify.TButton', background=[('active', '#ffe0a0')])
        self.tabs=ttk.Notebook(root)
        self.tabs.pack(fill='both',expand=True)
        self.photo_page=ttk.Frame(self.tabs);self.video_page=ttk.Frame(self.tabs)
        self.tabs.add(self.photo_page,text='Photos');self.tabs.add(self.video_page,text='Videos')
        from video_app import VideoApp
        self.video=VideoApp(self.video_page,embedded=True)
        self.astro_page=ttk.Frame(self.tabs)
        self.tabs.add(self.astro_page,text='AstroTrack')
        from astro.desktop import AstroPanel
        self.astro=AstroPanel(self.astro_page)
        self.tabs.bind('<<NotebookTabChanged>>',lambda event: self.astro.activate() if self.tabs.select()==str(self.astro_page) else None)

        header = ttk.Frame(self.photo_page, padding=(28, 22))
        header.pack(fill='x')
        ttk.Label(header, text='PhotoPeople', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='Your people, together.').pack(side='left', padx=20)
        self.scan_button = ttk.Button(header, text='+  Add photo folder', style='Accent.TButton', command=self.start_scan)
        self.scan_button.pack(side='right')
        self.photo_button = ttk.Button(header, text='+  Add photo', command=lambda: self.start_scan(single=True))
        self.photo_button.pack(side='right', padx=8)
        self.stats = ttk.Label(self.photo_page, padding=(28, 0), wraplength=1050)
        self.stats.pack(anchor='w')
        self.review_notice = ttk.Frame(self.photo_page, padding=(28, 8))
        self.review_notice.pack(fill='x')
        self.review_text = ttk.Label(self.review_notice, foreground='#744600')
        self.review_text.pack(side='left')
        self.review_button = ttk.Button(self.review_notice, text='! Review untagged photos',
            style='Identify.TButton', command=self.show_untagged)
        self.review_button.pack(side='left', padx=12)
        options = ttk.Frame(self.photo_page, padding=(28, 10))
        options.pack(fill='x')
        ttk.Label(options, text='Main subject only · Smaller background faces are ignored').pack(side='left')
        self.refresh_button = ttk.Button(options, text='Update existing photos', command=lambda: self.start_scan(refresh=True))
        self.refresh_button.pack(side='right')
        self.hidden_button = ttk.Button(options, text='Hidden people', command=self.toggle_hidden)
        self.hidden_button.pack(side='right', padx=8)
        ttk.Button(options,text='All photos',command=self.show_all).pack(side='right',padx=8)
        pet_bar = ttk.Frame(self.photo_page, padding=(28, 0))
        pet_bar.pack(fill='x')
        ttk.Label(pet_bar,text='Pets').pack(side='left',padx=(0,12))
        self.cat_button = ttk.Button(pet_bar,text='Cats',command=lambda:self.show_pets('cat'))
        self.cat_button.pack(side='left')
        self.dog_button = ttk.Button(pet_bar,text='Dogs',command=lambda:self.show_pets('dog'))
        self.dog_button.pack(side='left',padx=8)
        self.pet_scan_button = ttk.Button(pet_bar,text='Find pets in existing photos',command=lambda:self.start_scan(pets_only=True))
        self.pet_scan_button.pack(side='left')
        ttk.Label(pet_bar,text='Pet engine').pack(side='left',padx=(16,6))
        self.pet_backend=tk.StringVar(value=load_backend(self.store.folder))
        self.pet_engine=ttk.Combobox(pet_bar,textvariable=self.pet_backend,values=BACKENDS,
            state='readonly',width=10)
        self.pet_engine.pack(side='left')
        self.pet_engine.bind('<<ComboboxSelected>>',self.change_pet_backend)
        bar = ttk.Frame(self.photo_page, padding=(28, 18))
        bar.pack(fill='x')
        self.back = ttk.Button(bar, text='← People', command=self.show_people)
        self.back.pack(side='left')
        self.heading = ttk.Label(bar, text='People', font=('Segoe UI', 17, 'bold'))
        self.heading.pack(side='left', padx=15)
        self.name_button = ttk.Button(bar, text='Name person', command=self.rename)
        self.name_button.pack(side='right')
        self.merge_button = ttk.Button(bar, text='Merge into…', command=self.merge)
        self.merge_button.pack(side='right', padx=8)
        self.search = tk.StringVar()
        self.search_box = ttk.Entry(bar, textvariable=self.search, width=24)
        self.search_box.pack(side='right', padx=8)
        self.search.trace_add('write', lambda *_: self.render())
        self.canvas = tk.Canvas(self.photo_page, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self.photo_page, orient='vertical', command=self.canvas.yview)
        scroll.pack(side='right', fill='y')
        self.canvas.pack(fill='both', expand=True, padx=(28, 8))
        self.canvas.configure(yscrollcommand=scroll.set)
        self.content = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.content, anchor='nw')
        self.content.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        root.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta / 120), 'units') if self.tabs.select()==str(self.photo_page) else None)
        bottom = ttk.Frame(self.photo_page, padding=(28, 14))
        bottom.pack(fill='x')
        self.status = ttk.Label(bottom, text='Local library · Your originals stay untouched', wraplength=800)
        self.status.pack(side='left')
        ttk.Button(bottom,text='Videos',command=lambda:self.tabs.select(self.video_page)).pack(side='right')
        self.cancel_button = ttk.Button(bottom, text='Stop scan', command=self.cancel.set)
        self.progress = ttk.Progressbar(self.photo_page, mode='indeterminate')
        self.progress.pack(fill='x')
        self.show_people()
        self.poll_timer = root.after(100, self.poll)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def change_pet_backend(self,event=None):
        try:
            save_backend(self.store.folder,self.pet_backend.get())
        except OSError as exc:
            self.pet_backend.set(load_backend(self.store.folder))
            messagebox.showerror('Could not save pet engine',str(exc))
            return
        self.status.config(text=f"{self.pet_backend.get()} selected. Click Find pets in existing photos to rescan; corrections are kept.")

    def show_pets(self,kind):
        self.show_all()
        self.pet_kind=kind
        self.render()
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(0)

    def show_untagged(self):
        self.show_all()
        self.untagged_only = True
        self.render()

    def show_all(self):
        self.show_people()
        self.show_hidden = False
        self.all_view = True
        self.render()

    def edit_photo(self, photo, path):
        if self.busy:
            messagebox.showinfo('Scan in progress','Wait for the scan to finish before editing faces.')
            return
        from editor import FaceEditor
        FaceEditor(self,photo,path)

    def toggle_hidden(self):
        self.show_people(hidden=not self.show_hidden)

    def hide_person(self, person, hidden=True):
        if self.busy:
            return
        self.store.set_hidden(person, hidden)
        self.show_people(hidden=self.show_hidden)
        self.status.config(text=('Person hidden. Matching faces on future scans stay hidden. Restore from Hidden people.'
                                 if hidden else 'Person restored to People.'))

    def show_people(self, hidden=False):
        self.pet_kind = None
        self.show_hidden = hidden
        self.untagged_only = False
        self.all_view = False
        self.selected = None
        self.page = 0
        self.search.set('')
        self.render()
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(0)

    def person(self, person):
        self.selected = person
        self.page = 0
        self.render()
        self.canvas.yview_moveto(0)

    def thumbnail(self, path, size):
        try:
            with Image.open(path) as source:
                pic = ImageOps.exif_transpose(source).convert('RGB')
                pic.thumbnail(size)
        except Exception:
            pic = Image.new('RGB', size, '#d8dbe5')
        result = ImageTk.PhotoImage(pic)
        self.images.append(result)
        return result

    def render(self):
        if not hasattr(self, 'content'):
            return
        for child in self.content.winfo_children():
            child.destroy()
        self.images.clear()
        if self.selected is not None or self.all_view or self.show_hidden:
            self.back.pack(side='left', before=self.heading)
        else:
            self.back.pack_forget()
        counts = self.store.pet_counts()
        self.cat_button.config(text=f"Cats ({counts['cat']})")
        self.dog_button.config(text=f"Dogs ({counts['dog']})")
        people = self.store.people(hidden=self.show_hidden)
        visible_count = len(self.store.people())
        photos, faces = self.store.counts()
        summary = self.store.summary()
        self.stats.config(text=f"{summary['total']} photos scanned = {summary['with_faces']} with saved faces + {summary['without_faces']} without saved faces\n{visible_count} people groups · {summary['visible_faces']} saved face appearances · {summary['hidden_faces']} hidden appearances. A photo can include multiple people.")
        missing = summary['without_faces']
        self.review_text.config(text=f'{missing} photo' + ('s' if missing != 1 else '') + ' without saved face tags. Someone familiar may have been missed.')
        self.review_button.config(state='normal' if missing and not self.busy else 'disabled')
        self.hidden_button.config(text='Show people' if self.show_hidden else 'Hidden people')
        for button in (self.name_button, self.merge_button):
            button.config(state='normal' if self.selected is not None and not self.busy and not self.show_hidden else 'disabled')
        if self.all_view:
            self.heading.config(text='Untagged photos' if self.untagged_only else 'All photos')
            self.search_box.config(state='disabled')
            rows = self.store.all_photos()
            if self.pet_kind:
                self.heading.config(text='Cats' if self.pet_kind=='cat' else 'Dogs')
                rows=self.store.pet_photos(self.pet_kind)
            if self.untagged_only:
                rows = [row for row in rows if not self.store.photo_labels(row['id'])]
        elif self.selected is None:
            self.heading.config(text='Hidden people' if self.show_hidden else 'People')
            self.search_box.config(state='normal')
            rows = [p for p in people if self.search.get().lower() in (p['name'] or f'Person {p["id"]}').lower()]
        else:
            person = next((p for p in people if p['id'] == self.selected), None)
            self.heading.config(text=(person['name'] or f'Person {person["id"]}') if person else 'Empty group')
            self.search_box.config(state='disabled')
            rows = self.store.photos(self.selected)
        if not rows and self.pet_kind:
            ttk.Label(self.content,text='No ' + ('cats' if self.pet_kind=='cat' else 'dogs') + ' detected yet',font=('Segoe UI',22,'bold')).pack(pady=(55,15))
            ttk.Label(self.content,text='Add a photo or use Find pets in existing photos. Detection can miss small or obscured animals.').pack()
            return
        if not rows:
            title = ('No hidden people' if self.show_hidden else ('Meet the people in your photos' if not photos else 'No matching people here'))
            ttk.Label(self.content, text=title, font=('Segoe UI', 22, 'bold')).pack(pady=(65, 15))
            if self.show_hidden:
                ttk.Label(self.content, text='People you choose not to remember will appear here. You can restore them anytime.').pack(pady=10)
                return
            ttk.Label(self.content, text='Add a folder to find familiar faces and bring their photos together.\n\nSupports JPG, PNG, WebP, BMP and TIFF, including subfolders.\nName groups yourself, and correct matches as you browse.', justify='center').pack(pady=10)
            return
        start = self.page * 24
        if start >= len(rows):
            self.page = 0
            start = 0
        grid = ttk.Frame(self.content)
        grid.pack(fill='x')
        for col in range(4):
            grid.columnconfigure(col, weight=1)
        for i, row in enumerate(rows[start:start + 24]):
            card = tk.Frame(grid, background='white', padx=12, pady=14)
            card.grid(row=i // 4, column=i % 4, padx=7, pady=7, sticky='nsew')
            if self.selected is None and not self.all_view:
                image = self.thumbnail(self.store.thumbs / (row['thumb'] or 'missing.jpg'), (150, 150))
                action = lambda p=row['id']: self.person(p)
                name = row['name'] or f'Person {row["id"]}'
                detail = f'{row["count"]:,} photo' + ('s' if row['count'] != 1 else '')
            else:
                image = self.thumbnail(row['path'], (200, 150))
                action = lambda p=row['path'], i=row['id']: self.edit_photo(i,p)
                name = Path(row['path']).name
                labels = self.store.photo_labels(row['id'])
                pet_labels=sorted({r['species'].title() for r in self.store.pet_detections(row['id'])})
                detail = 'Tagged: ' + (', '.join(labels) or 'No people yet')
                if pet_labels: detail += '\nPets: ' + ', '.join(pet_labels)
            tk.Button(card, image=image, command=action, relief='flat', bg='white', cursor='hand2').pack()
            tk.Label(card, text=name, bg='white', fg=INK, font=('Segoe UI', 11, 'bold'), wraplength=190).pack(pady=(9, 3))
            tk.Label(card, text=detail, bg='white', fg='#686f81', font=('Segoe UI', 9), wraplength=190).pack()
            if self.selected is None and not self.all_view:
                ttk.Button(card, text='Remember this person' if self.show_hidden else "Don't remember this person",
                    command=lambda p=row['id'], h=not self.show_hidden: self.hide_person(p, h),
                    state='disabled' if self.busy else 'normal').pack(pady=(8, 0))
            if self.selected is not None or self.all_view:
                if not labels and not pet_labels:
                    tk.Label(card, text='A familiar face may have been missed. Select a face to tell us who it is.',
                        bg='white', fg='#744600', font=('Segoe UI',9), wraplength=190).pack(pady=(8,0))
                ttk.Button(card, text='View photo / tags' if pet_labels else ('Choose faces' if labels else '! Identify someone'),
                    style='TButton' if labels or pet_labels else 'Identify.TButton', command=lambda p=row['path'], i=row['id']: self.edit_photo(i,p),
                    state='disabled' if self.busy else 'normal').pack(pady=(8,0))
                for kind in sorted({r['species'] for r in self.store.pet_detections(row['id'])}):
                    ttk.Button(card,text=f'No {kind} in this photo',
                        command=lambda p=row['id'],k=kind:self.reject_pet(p,k),
                        state='disabled' if self.busy else 'normal').pack(pady=(4,0))
                ttk.Button(card, text='Open original', command=lambda p=row['path']:self.open_photo(p)).pack(pady=(4,0))
            if self.selected is not None:
                ttk.Button(card, text='Use face as group thumbnail',
                    command=lambda f=row['face_id']: self.set_group_cover(f),
                    state='disabled' if self.busy else 'normal').pack(pady=(4,0))
            if self.selected is not None and not self.show_hidden:
                ttk.Button(card, text='Move saved face to new group', command=lambda f=row['face_id']: self.separate(f),
                    state='disabled' if self.busy else 'normal').pack(pady=(8, 0))
        pager = ttk.Frame(self.content, padding=15)
        pager.pack()
        ttk.Button(pager, text='Previous', command=lambda: self.change_page(-1), state='normal' if self.page else 'disabled').pack(side='left')
        ttk.Label(pager, text=f'  {start + 1}–{min(start + 24, len(rows))} of {len(rows)}  ').pack(side='left')
        ttk.Button(pager, text='Next', command=lambda: self.change_page(1), state='normal' if start + 24 < len(rows) else 'disabled').pack(side='left')

    def reject_pet(self, photo, species, rejected=True):
        if self.busy:return
        self.store.reject_pet(photo,species,rejected)
        self.render()
        self.status.config(text=(f'Photo excluded from {species.title()}s. This correction survives rescans. Undo in View photo / tags from All photos.'
                                 if rejected else f'{species.title()} detection restored.'))

    def set_group_cover(self, face):
        if self.busy or self.selected is None:
            return
        try:
            self.store.set_cover(self.selected, face)
            self.status.config(text='Group thumbnail updated. Return to People to see it.')
            self.render()
        except (OSError, ValueError) as exc:
            messagebox.showerror('Cannot update thumbnail', str(exc))

    def change_page(self, delta):
        self.page += delta
        self.render()
        self.canvas.yview_moveto(0)

    def open_photo(self, path):
        try:
            os.startfile(path)
        except OSError as exc:
            messagebox.showerror('Cannot open photo', str(exc))

    def rename(self):
        person = next(p for p in self.store.people() if p['id'] == self.selected)
        name = simpledialog.askstring('Name this person', 'Who is this?', initialvalue=person['name'], parent=self.root)
        if name is not None:
            self.store.rename(self.selected, name)
            self.render()

    def merge(self):
        choices = [p for p in self.store.people() if p['id'] != self.selected]
        if not choices:
            messagebox.showinfo('Merge groups', 'Add more photos to find another group first.')
            return
        dialog = tk.Toplevel(self.root)
        dialog.title('Merge people groups')
        dialog.geometry('420x180')
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text='These are the same person. Merge into:', padding=15).pack()
        picker = ttk.Combobox(dialog, state='readonly', width=42, values=[f'{p["name"] or "Unnamed"} · Group {p["id"]} · {p["count"]} photos' for p in choices])
        picker.pack(padx=15)
        picker.current(0)
        def confirm():
            target = choices[picker.current()]['id']
            self.store.merge(self.selected, target)
            dialog.destroy()
            self.person(target)
        ttk.Button(dialog, text='Merge groups', command=confirm).pack(pady=15)

    def separate(self, face):
        self.store.separate(face)
        self.render()
        self.status.config(text='Face moved into a new unnamed group. Find it under People.')

    def start_scan(self, refresh=False, single=False, pets_only=False):
        if self.busy:
            return
        folder, paths = None, None
        if single:
            filename = filedialog.askopenfilename(title='Select a photo', filetypes=[
                ('Photos', '*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff'), ('All files', '*.*')])
            if not filename:
                return
            paths = [Path(filename)]
        elif not refresh and not pets_only:
            folder = filedialog.askdirectory(title='Select a photo folder')
            if not folder:
                return
        backend=self.pet_backend.get()
        self.pet_engine.config(state='disabled')
        self.busy = True
        self.cancel.clear()
        self.scan_button.config(state='disabled')
        self.photo_button.config(state='disabled')
        self.pet_scan_button.config(state='disabled')
        self.refresh_button.config(state='disabled')
        self.cancel_button.pack(side='right')
        self.progress.start()
        self.render()
        def work():
            indexer = None
            pet_store = None
            try:
                progress = lambda text: self.events.put(('progress', text))
                if pets_only:
                    pet_store = Store(self.store.folder)
                    result = dict(imported=0,skipped=0,faces=0,errors=[],cancelled=False)
                else:
                    indexer = Indexer(progress, data=self.store.folder)
                    pet_store = indexer.store
                    result = (indexer.refresh_library(progress, self.cancel) if refresh
                              else indexer.scan(folder, progress, self.cancel, paths=paths))
                try:
                    from pets import scan_pets
                    pets=scan_pets(pet_store,progress,self.cancel,backend=backend)
                    result['pet_photos']=pets['processed']
                    result['errors'].extend(pets['errors'])
                    result['cancelled']=result['cancelled'] or pets['cancelled']
                except Exception as exc:
                    result['errors'].append('Pet detection: ' + str(exc))
                self.events.put(('done', result))
            except Exception as exc:
                self.events.put(('error', str(exc)))
            finally:
                if pet_store is not None:
                    pet_store.close()
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'progress':
                    self.status.config(text=value)
                else:
                    self.busy = False
                    self.pet_engine.config(state='readonly')
                    self.scan_button.config(state='normal')
                    self.photo_button.config(state='normal')
                    self.pet_scan_button.config(state='normal')
                    self.refresh_button.config(state='normal')
                    self.cancel_button.pack_forget()
                    self.progress.stop()
                    if kind == 'error':
                        self.status.config(text='Scan failed. Your existing library is still available.')
                        messagebox.showerror('Scan failed', value)
                    else:
                        prefix = 'Stopped' if value['cancelled'] else 'Finished'
                        self.status.config(text=f"{prefix} · {value['imported']} photos processed · {value['faces']} faces · {value.get('pet_photos',0)} checked for pets · {value['skipped']} unchanged/duplicate photos skipped · {len(value['errors'])} errors")
                        if value['errors']:
                            messagebox.showwarning('Some photos could not be read', '\n'.join(value['errors'][:10]))
                    self.render()
        except queue.Empty:
            pass
        self.poll_timer = self.root.after(100, self.poll)

    def close(self):
        if self.video.running():
            self.video.close();self.cancel.set();self.tabs.select(self.video_page)
            self.root.after(100,self.close)
            return
        if self.busy:
            self.cancel.set()
            self.status.config(text='Stopping after the current photo; close again when the scan finishes.')
            return
        if self.astro.busy:
            self.astro.closing=True
            self.astro.status.config(text='Finishing the AstroTrack operation before closing…')
            self.root.after(100,self.close)
            return
        self.progress.stop()
        self.video.dispose()
        self.astro.dispose()
        self.root.after_cancel(self.poll_timer)
        self.store.close()
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
