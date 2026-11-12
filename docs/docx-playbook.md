# Word (.docx) playbook for agents

Agents make Word documents rarely, and every time they hit the same traps: `python-docx` has an API that
**looks like it works** while Word partly ignores it. This file is the verified experience, so it isn't
rediscovered. Add only **confirmed** findings (you saw it work), not guesses. Append at the bottom, dated.

## 0. Never hand over a file you haven't looked at

`python-docx` does not render. It writes XML. You can set widths, fonts and orientation, get zero errors,
and still deliver a broken document. (See §2.)

Mandatory verification loop:

```bash
# 1. docx -> pdf
soffice --headless --convert-to pdf --outdir <dir> <file>.docx
# 2. pdf -> png
pdftoppm -png -r 110 <file>.pdf page
# 3. look at page-1.png with an image-reading tool
```

LibreOffice does not render pixel-for-pixel like Word, but every gross failure (broken words, shifted
columns, text outside the page, bad wraps) shows the same. That is enough. `-r 110` keeps small table text
readable without a bloated image.

Do not skip this on a "simple" document. The incident below was a simple table: the bug was not in the
code, but in how Word reads the file.

## 1. Tools

- `python-docx` (1.2.0 tested). `import docx`.
- LibreOffice (`soffice`) and `pdftoppm` for verification.
- For XML surgery (you will need it): `from docx.oxml import OxmlElement`, `from docx.oxml.ns import qn`.

## 2. Main trap: Word ignores column widths

**Symptom.** You set widths; all columns come out equal. In narrow columns, words **break mid-word**
("water-intak / e facili / ties"). It looks like a font or hyphenation problem. It isn't.

**Cause.** `cell.width = Cm(2.7)` writes the width into **each cell** (`w:tcW`). But Word and LibreOffice
take the real layout from **`w:tblGrid`**, the skeleton of the grid at the top of the table. `python-docx`
creates it in `add_table()` with equal columns and **does not update it** when you change cells. Cells
say one thing, the grid another; the grid wins.

**Fix (confirmed).** Write widths into `tblGrid` **and** lock auto-layout:

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

table.autofit = False

# 1) lock auto-layout, or Word recalculates the grid from content
layout = OxmlElement("w:tblLayout")
layout.set(qn("w:type"), "fixed")
table._tbl.tblPr.append(layout)

# 2) write widths into the grid itself (twips: 1 cm = 567)
for gc, w_cm in zip(table._tbl.tblGrid.findall(qn("w:gridCol")), WIDTHS_CM):
    gc.set(qn("w:w"), str(int(round(w_cm * 567))))

# 3) and into the cells too, for compatibility
for i, w_cm in enumerate(WIDTHS_CM):
    table.columns[i].width = Cm(w_cm)
    for row in table.rows:
        row.cells[i].width = Cm(w_cm)
```

All three steps are needed. `fixed` without `tblGrid` locks the wrong grid. `tblGrid` without `fixed`
lets Word recalculate.

## 3. Landscape: two independent switches

`sec.orientation = WD_ORIENT.LANDSCAPE` **does not swap the page size**; it only sets a flag. Without a
manual swap you get a portrait page flagged landscape.

```python
from docx.enum.section import WD_ORIENT
sec = doc.sections[0]
sec.orientation = WD_ORIENT.LANDSCAPE
sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)   # A4, by hand, required
```

**Usable width** = `page_width - left_margin - right_margin`. A4 landscape with 1.5 cm margins gives
**26.7 cm**; the column widths must sum to at most that, or the table runs past the margin. Compute before
writing, not after.

## 4. Vertical (rotated) text in a cell

Needed when the column is narrow and the label long (common in form-style tables). **No API**, XML only:

```python
def set_cell_vertical(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    td = OxmlElement("w:textDirection")
    td.set(qn("w:val"), "btLr")     # bottom-to-top, left-to-right
    tcPr.append(td)
```

`btLr` reads bottom-to-top. `tbRl` reads top-to-bottom. **Set the row height by hand**
(`row.height = Cm(7.2)`): rotated text does not get automatic height the way you want, and a long label
gets cut off.

## 5. Non-Latin text and fonts

Setting `run.font.name` is not enough; Word looks at a separate attribute for some character ranges:

```python
run.font.name = "Times New Roman"
run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
```

Same for the `Normal` style: `style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)`. Without it, part of
the text can fall back to another font. Working sizes: 9–10 pt for dense tables, 11–12 pt for body text.

## 6. Cells: the empty paragraph and borders

- `cell.text = "..."` replaces content, but **a cell always has at least one paragraph**. For multi-line
  text, put the first line in `cell.paragraphs[0]` and use `cell.add_paragraph()` for the rest. If every
  line goes through `add_paragraph()`, an empty line stays on top.
- Set `space_before` / `space_after` to `Pt(0)` in every cell paragraph, or the content "floats" in a dense table.
- **Borders:** the default table style may have no lines. Reliable: set `w:tcBorders` on every cell
  (`w:val=single`, `w:sz=6`, about 0.75 pt).

## 7. Delivering the file

Use the swarm's one sanctioned channel for handing files to the human, documented in one place. Do not
start your own web server for it: a permission classifier may block it, and a verbal OK does not lift the block.

## 8. Recreating a document from a photo

- Read **orientation and structure** from the photo; don't assume. Photos are often rotated, so columns look like rows.
- Labels that read "backwards" relative to the rest are not a photo defect; they are **vertical text** in the original (§4).
- A column-number row ("1 2 3 ...") in form-style documents is a real table row, not decoration. Carry it over as a row.
- Small or handwritten text: tell the human exactly what you read uncertainly and let them correct it. Do not fill in for them.

## 9. Not yet verified (verify, then add)

Merged cells, repeating the header row across pages (`w:tblHeader`), headers/footers, page numbers, images
inside cells, document protection, using an existing .docx as a template (open, edit, save).

## Entries

**Case: a 13-column landscape table recreated from a photo (2026-08).** Three columns with vertical labels
plus a numbering row. Cost: **§2** (widths not applied; two wasted runs because "the code looks right")
and delivery (four blocked attempts). What saved it: **§0** — the PNG render showed broken words that were
invisible in the code.

**`.pptx` conversion (2026-10).** `soffice --convert-to pdf` on a .pptx answered "source file could not be
loaded" although python-pptx opened the file. Cause: only `libreoffice-writer` (+core/common) was
installed; the Impress component was missing, and §0 above was written for .docx. Fix (confirmed):
`apt-get install -y libreoffice-impress` (about 10 minutes — run it in the background, a foreground shell
may time out at 8 minutes). Two more traps the same evening: (1) `soffice` could not read a file from a
sandboxed temp directory — convert a copy placed in the project folder, by absolute path; (2)
`addImage({rounding:true})` in pptxgenjs makes an **ellipse**, not rounded corners — for a rounded
"screen", put the image on a roundRect backing.
