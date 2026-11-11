# 🐾 Patas Solidárias – Controle de Estoque

Sistema web para uma ONG de proteção animal controlar produtos, doações e consumo.
Projeto de **Atividades de Extensão II** – CST em Análise e Desenvolvimento de Sistemas (2º semestre, 2026/2).

> Todos os dados são fictícios, apenas para demonstração. Não há dados pessoais nem informações reais de animais.

## 1. Como executar

Requisito: **Python 3.8 ou superior** (https://www.python.org). Não é preciso instalar mais nada.

```
cd patas_solidarias
python app.py          (no Linux/Mac, se necessário: python3 app.py)
```

O navegador abre sozinho em **http://localhost:8000**. Para encerrar, use `Ctrl+C` no terminal.
Na primeira execução o banco é criado com os dados de demonstração. Para voltar ao estado inicial, feche o sistema e apague o arquivo `patas_solidarias.db`.

Para rodar os testes automáticos: `python testes.py` (usa um banco temporário e não altera os seus dados).

## 2. Arquivos

| Arquivo | Função |
|---|---|
| `app.py` | Back-end: servidor web, regras de negócio e acesso ao banco SQLite |
| `index.html` | Front-end: telas, estilos (CSS) e comportamento (JavaScript) |
| `testes.py` | 30 testes automáticos das funcionalidades e regras |
| `patas_solidarias.db` | Banco de dados (criado automaticamente na primeira execução) |

Tecnologias: HTML, CSS e JavaScript no front-end; Python (biblioteca padrão) no back-end; SQLite no banco. O front-end conversa com o back-end por requisições HTTP que trocam dados em JSON (`/api/...`).

## 3. Banco de dados

SQLite guarda tudo em **um único arquivo**, por isso os dados continuam salvos ao fechar e abrir o sistema.

**produtos**: `id`, `codigo` (único), `nome`, `categoria`, `descricao`, `quantidade`, `minimo`, `unidade`, `data_cadastro`.
**movimentacoes**: `id`, `produto_id`, `codigo`, `produto_nome`, `unidade`, `tipo` (entrada/saída), `motivo` (Doação, Compra, Estoque inicial ou Uso), `quantidade`, `data`, `detalhe` (origem da entrada ou finalidade da saída), `observacoes`.

Relação: um produto tem várias movimentações (1:N).

Como as regras são garantidas:
- **Sem estoque negativo:** o banco tem `CHECK(quantidade >= 0)` e o programa recusa a saída maior que o saldo, com mensagem clara.
- **Histórico sempre gerado:** toda alteração de quantidade passa pela função `mover()`, que atualiza o saldo e grava a movimentação na mesma transação (se algo falhar, nada é salvo). A quantidade inicial de um produto novo também vira uma movimentação "Estoque inicial".
- **Exclusão de produto:** o histórico é mantido, pois a movimentação guarda uma cópia do nome e do código.
- **Datas:** guardadas como AAAA-MM-DD (formato que ordena corretamente) e exibidas como DD/MM/AAAA.

## 4. Como usar cada funcionalidade

- **Dashboard:** cartões com total de produtos, disponíveis, estoque baixo e sem estoque; alertas (vermelho = sem estoque, amarelo = abaixo do mínimo); resumo de entradas e saídas; últimas movimentações.
- **Produtos:** botão *Novo produto*; preencha nome, categoria, mínimo e unidade (o código é gerado automaticamente, ex.: PS-009, mas pode ser digitado). Use os filtros de busca, categoria e situação. *Editar* altera os dados cadastrais (a quantidade só muda por entrada/saída). O botão 🗑️ pede confirmação antes de excluir.
- **Entrada de produtos:** escolha o produto, quantidade, data, tipo (Doação ou Compra), origem e observações. O estoque aumenta na hora.
- **Saída de produtos:** escolha produto, quantidade, data e finalidade (alimentação, tratamento, higiene, limpeza...). O estoque diminui; se a quantidade for maior que o saldo, o sistema bloqueia.
- **Histórico:** lista todas as movimentações, com filtros por produto, tipo e período.
- **Relatórios:** estoque geral, doações recebidas, produtos utilizados e produtos em falta (com sugestão de reposição). Os dois relatórios de movimentação aceitam filtro de período. O botão *Exportar CSV* baixa o arquivo (separador `;` e acentos corretos, abre direto no Excel em português).

## 5. Dados de demonstração (fictícios)

Ração para cães adultos 15 kg · Ração para filhotes 10 kg · Vermífugo 5 un (abaixo do mínimo, gera alerta) · Antisséptico 8 un · Shampoo para cães 6 un · Desinfetante para canis 12 un · Coleiras 10 un · Vacina antirrábica 0 un (exemplo de "sem estoque").

## 6. Relação com o Guia de Extensão

| Etapa do guia | O que este projeto entrega |
|---|---|
| 1ª – Identificação da instituição | ONG fictícia de proteção animal; levantamento: controle manual dificulta saber saldos, doações e consumo |
| 2ª – Análise e planejamento | Requisitos (seção 2 do enunciado) e modelagem das duas tabelas (seção 3 deste documento) |
| 3ª – Desenvolvimento | Este sistema (solução simples, com banco de dados básico) |
| 4ª – Apresentação e validação | Demonstrar o sistema aos responsáveis da instituição e coletar a percepção de uso |
| Etapa final – Documentação | Este README, prints das telas, relatório CSV exportado e o formulário de comprovação assinado |

Observação: como a ONG deste projeto é fictícia, confirme com seu professor ou tutor como cumprir as etapas 1 e 4 (contato e validação com a instituição) e quais comprovantes (fotos, formulário assinado, relatório) devem ser anexados na plataforma.
