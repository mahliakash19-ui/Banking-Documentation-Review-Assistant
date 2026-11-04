# Evaluation (fictional sample agreement)

Retrieval over 18 checklist items: answer clause ranked first for 17/18, within top 3 for 18/18.

| item                | expected   | retrieved        | top1   | top3   |
|:--------------------|:-----------|:-----------------|:-------|:-------|
| facility_amount     | 1.1/2.1    | 11.4, 1.1, 2.1   | False  | True   |
| tenor               | 1.1/2.3    | 1.1, 2.3, 1.1    | True   | True   |
| currencies          | 2.2        | 2.2, 5.1, 4.3    | True   | True   |
| margin              | 5.2        | 5.2, 6.2, 5.1    | True   | True   |
| reference_rates     | 5.1/5.3    | 5.3, 5.1, 9.2    | True   | True   |
| commitment_fee      | 6.1        | 6.1, 6.4, 6.2    | True   | True   |
| utilisation_fee     | 6.2        | 6.2, 6.4, 4.3    | True   | True   |
| agency_fee          | 6.3        | 6.3, 6.4, 6.2    | True   | True   |
| utilisation_notice  | 4.1        | 4.1, 4.3, 2.3    | True   | True   |
| prepayment_notice   | 7.1        | 7.1, 7.2, 4.2    | True   | True   |
| cancellation_notice | 7.2        | 7.2, 4.2, 7.1    | True   | True   |
| change_of_control   | 7.3/1.1    | 7.3, 1.1, 6.1    | True   | True   |
| financial_covenant  | 9.1        | 9.1, 9.2, 1.1    | True   | True   |
| reporting_deadlines | 8.1/8.2    | 8.2, 8.1, 9.2    | True   | True   |
| negative_pledge     | 10.1       | 10.1, 11.1, 9.1  | True   | True   |
| cross_default       | 11.2       | 11.2, 11.4, 11.3 | True   | True   |
| majority_lenders    | 11.4       | 11.4, 2.1, 6.2   | True   | True   |
| governing_law       | 13.1/13.2  | 13.2, 13.1, 1.1  | True   | True   |

Grounding checks: 5/5 cases handled as expected.

| case                 | expected   | result   | correct   |
|:---------------------|:-----------|:---------|:----------|
| correct answer       | pass       | pass     | True      |
| wrong number         | reject     | reject   | True      |
| invented quote       | reject     | reject   | True      |
| clause not retrieved | reject     | reject   | True      |
| honest not-found     | pass       | pass     | True      |
