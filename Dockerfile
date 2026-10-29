import fitz # PyMuPDF
doc = fitz.open("Dockerfile_Rehberi.pdf")
text = ""
for page in doc:
    text += page.get_text()
print(text)