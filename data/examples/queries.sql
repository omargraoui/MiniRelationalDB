SELECT * FROM departments;

SELECT name, salary FROM employees
WHERE salary > 70000 AND active = TRUE ORDER BY salary DESC;

SELECT department_id, COUNT(*), SUM(salary), AVG(salary), MIN(salary), MAX(salary)
FROM employees GROUP BY department_id ORDER BY department_id;

SELECT employees.name, departments.name FROM employees
INNER JOIN departments ON employees.department_id = departments.id
ORDER BY employees.name;

SELECT name, salary FROM employees WHERE id = 3;
