import pypdf
import re
import logging
from pathlib import Path
import csv

logging.getLogger().setLevel(logging.INFO)


def main():
  ## Get all files
  folder_path = Path("input")
  registers = []
  for doc in folder_path.iterdir():
    if doc.is_file() and doc.name != ".gitkeep":
      file_extension = doc.suffix
      if file_extension != ".pdf":
        registers.extend(processCSV(doc))
      else:
        registers.extend(processPDF(doc))
  save(registers)


def format_money(text):
  return float(
    text.replace("R$", "").replace(".", "").replace(",", ".").replace(" ", "")
  )


def find_monetary(text):
  return re.search("R\$\s[0-9\.]+,[0-9]{2}", text)


def find_last_payment(text):
  return re.search("Pagamento em.+", text)


def find_iof(text):
  return re.search("Repasse de IOF em R\$", text)


def add_zero_if_needed(num):
  if num >= 1 and num <= 9:
    return "0" + str(num)
  else:
    return str(num)


def find_date(text, month, year):
  match = re.search("^([0-9]{2})\s(\w{3})$", text)
  if not match:
    return None

  matchDay = add_zero_if_needed(int(match.group(1)))
  matchMonth = add_zero_if_needed(month_string_to_number(match.group(2)))
  matchYear = year - 1 if matchMonth == 12 and month == 1 else year
  return f"{matchYear}-{matchMonth}-{matchDay}"


def month_string_to_number(month):
  month_lower = month.lower()
  match month_lower:
    case "jan":
      return 1
    case "fev":
      return 2
    case "mar":
      return 3
    case "abr":
      return 4
    case "mai":
      return 5
    case "jun":
      return 6
    case "jul":
      return 7
    case "ago":
      return 8
    case "set":
      return 9
    case "out":
      return 10
    case "nov":
      return 11
    case "dez":
      return 12


def find_postage_date(text):
  match = re.search(r"Data de vencimento:\s\d{2}\s(\w{3})\s(\d{4})", text)
  if match:
    month = month_string_to_number(match.group(1))
    year = int(match.group(2))
    return [month, year]


def get_visitor_body(array, page):
  def visitor_body_fn(text, cm, tm, font_dict, font_size):
    if text.strip() == "":
      return
    y = tm[5]
    if y > 720 or y < 70:
      return
    array.append(text)

  return visitor_body_fn


def processCSV(doc):
  doc_name = doc.name
  registers = []
  with open(doc, "r") as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
      date = row[0]
      description = row[1]
      value = float(row[2])
      if description.lower() != "pagamento recebido":
        registers.append(
          [
            doc_name,
            date,
            description,
            value,
          ]
        )

  return registers


def processPDF(doc):
  doc_name = doc.name
  reader = pypdf.PdfReader(doc)
  pages = [i for i in range(4, len(reader.pages))]
  dict = {"doc_name": doc_name, "month": None, "year": None, "total_value": 0}

  ## Get month and year
  first_page = reader.pages[0].extract_text().split("\n")
  for line in first_page:
    postage_date = find_postage_date(line)
    if postage_date:
      dict["month"], dict["year"] = postage_date
      continue
    if find_monetary(line) and dict["total_value"] == 0:
      dict["total_value"] = format_money(line)
      continue

  ## Get all data from pages with tables
  parts = []
  for page in pages:
    pageParts = []
    reader.pages[page].extract_text(visitor_text=get_visitor_body(pageParts, page))

    parts.extend(pageParts)

  logging.debug(f'"{doc.name}" pages: ' + str(len(reader.pages)))
  return processParts(dict, parts)


def processParts(dict, parts):
  doc_name = dict["doc_name"]
  month = dict["month"]
  year = dict["year"]
  sum = 0
  registers = []
  index = 0
  while index < len(parts):
    value = format_money(parts[index + 2])
    date = find_date(parts[index], month, year)
    description = parts[index + 1]

    index += 3
    if find_last_payment(description) is None:
      sum += value
      registers.append(
        [
          doc_name,
          date,
          description,
          value,
        ]
      )

  total_value = dict["total_value"]

  if abs(sum - total_value) > 0.01:
    logging.error(
      f"Values don't match. Sum: {sum}, Total: {total_value}, doc_name: {doc_name}"
    )
    # logging.error(registers)
    logging.error(list(map(lambda x: f"{x[1]}-{x[2]}-{x[3]}", registers)))

    raise Exception("Values don't match")

  logging.debug(f'"{doc_name}" total value: ' + str(round(sum, 2)))
  logging.debug(f'"{doc_name}" registers  : ' + str(len(registers)))
  return registers

def save(registers):
  sep = ";"
  with open("output/ouput.csv", "w") as f:
    t = [
      [
        register if isinstance(register, str) else str(register).replace(".", ",")
        for register in row
      ]
      for row in registers
    ]
    data = sep.join(["filename", "date", "description", "value"]) + "\n"
    data += "\n".join([sep.join(register) for register in t])
    f.write(data)

  logging.debug(registers)
  logging.info("total of registers " + str(len(registers)))
  logging.info("total of money " + str(sum([r[-1] for r in registers])))


if __name__ == "__main__":
  main()

