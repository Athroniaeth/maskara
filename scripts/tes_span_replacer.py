from span_replacer import SpanReplacer, Span

text = "Bonjour je m'appelle Patrick, j'ai 25 ans, c'est un beau prénom Patrick non ?"
spans = [Span(21, 28, "{name_1}"), Span(35, 41, "{age_1}"), Span(64, 71, "{name_1}")]
print(f"Original text: {text}")
print(f"Spans: {spans}\n")

replacer = SpanReplacer()
result = replacer.apply(text, spans)

print(f"Replaced text: {result.text}")
print(f"Spans: {spans}")
print(f"Restored text: {replacer.restore(result)}\n")

result_2 = replacer.apply(result.text, result.reverse_spans)
print(f"Recursive apply replaced text: {result_2.text}")
print(f"Recursive apply spans: {spans}")
print(f"Recursive apply restored text: {replacer.restore(result_2)}\n")