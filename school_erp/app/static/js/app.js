function toNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const num = Number(value);
  return Number.isNaN(num) ? null : num;
}

function parseByType(raw, type) {
  if (type === "number") return toNumber(raw);
  if (type === "entity-select") return toNumber(raw) ?? raw;
  if (type === "csv-int") {
    return String(raw || "")
      .split(",")
      .map((x) => Number(x.trim()))
      .filter((x) => Number.isInteger(x));
  }
  return raw;
}

const ENTITY_CACHE = {};

const ENTITY_SOURCES = {
  classes: {
    url: "/api/v1/directory/classes",
    valueKey: "id",
    label: (row) => `${row.name} (${row.academic_year})`,
  },
  students: {
    url: "/api/v1/directory/students",
    valueKey: "id",
    label: (row) => `${row.full_name}${row.admission_no ? ` - ${row.admission_no}` : ""}`,
  },
  subjects: {
    url: "/api/v1/directory/subjects",
    valueKey: "id",
    label: (row) => `${row.name}${row.code ? ` (${row.code})` : ""}`,
  },
  users: {
    url: "/api/v1/directory/users",
    valueKey: "id",
    label: (row) => `${row.full_name}${row.username ? ` (${row.username})` : ""}`,
  },
  attendance_sessions: {
    url: "/api/v1/attendance/sessions",
    valueKey: "id",
    label: (row) => `Session #${row.id} - Class ${row.class_id} (${row.session_date})`,
  },
  ocr_batches: {
    url: "/api/v1/attendance/ocr/batches",
    valueKey: "id",
    label: (row) => `Batch #${row.id} - ${row.parse_status} (${row.line_count || 0} lines)`,
  },
  exams: {
    url: "/api/v1/exams",
    valueKey: "id",
    label: (row) => `${row.name} (${row.status})`,
  },
  threads: {
    url: "/api/v1/messages/threads",
    valueKey: "id",
    label: (row) => `${row.title || `Thread #${row.id}`} (${row.thread_type})`,
  },
};

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch (_err) {
    payload = null;
  }

  if (!response.ok) {
    const message = payload?.error?.message || `Request failed (${response.status})`;
    throw new Error(message);
  }

  return payload;
}

function fieldTemplate(actionKey, field) {
  const id = `${actionKey}-${field.name}`;
  const required = field.required ? "required" : "";
  const placeholder = field.placeholder ? `placeholder="${field.placeholder}"` : "";
  const help = field.help ? `<small class="field-help">${field.help}</small>` : "";

  if (field.type === "select") {
    const options = (field.options || [])
      .map((opt) => `<option value="${opt.value}">${opt.label}</option>`)
      .join("");
    return `<label class="field"><span>${field.label}</span><select id="${id}" name="${field.name}" ${required}>${options}</select>${help}</label>`;
  }

  if (field.type === "entity-select") {
    const blank = field.required ? `<option value="">Select ${field.label}</option>` : `<option value="">Optional</option>`;
    return `<label class="field"><span>${field.label}</span><select id="${id}" name="${field.name}" data-entity-source="${field.source}" ${required}>${blank}<option value="">Loading options...</option></select>${help}</label>`;
  }

  if (field.type === "textarea") {
    return `<label class="field"><span>${field.label}</span><textarea id="${id}" name="${field.name}" ${required} ${placeholder}></textarea>${help}</label>`;
  }

  const inputType = field.type === "datetime" ? "datetime-local" : field.type || "text";
  return `<label class="field"><span>${field.label}</span><input id="${id}" type="${inputType}" name="${field.name}" ${required} ${placeholder} />${help}</label>`;
}

function getFormValues(form, fields) {
  const data = {};
  for (const field of fields) {
    const el = form.querySelector(`[name="${field.name}"]`);
    if (!el) continue;
    const raw = el.value;
    const parsed = parseByType(raw, field.valueType || field.type);

    if (parsed === "" || parsed === null || parsed === undefined) {
      if (field.required) {
        throw new Error(`${field.label} is required`);
      }
      continue;
    }
    data[field.name] = parsed;
  }
  return data;
}

function objectToTable(data, columns) {
  const thead = columns.map((c) => `<th>${c.label}</th>`).join("");
  const rows = data
    .map((row) => {
      const tds = columns
        .map((col) => {
          let value = row[col.key];
          if (value === null || value === undefined) value = "-";
          if (typeof value === "object") value = JSON.stringify(value);
          return `<td>${value}</td>`;
        })
        .join("");
      return `<tr>${tds}</tr>`;
    })
    .join("");

  return `<table class="erp-table"><thead><tr>${thead}</tr></thead><tbody>${rows || `<tr><td colspan="${columns.length}">No records found.</td></tr>`}</tbody></table>`;
}

function renderResultData(data) {
  if (data === null || data === undefined) return "<p>No details were returned.</p>";

  if (Array.isArray(data)) {
    if (!data.length) return "<p>No records available.</p>";
    const preview = data.slice(0, 6).map((item) => `<li>${typeof item === "object" ? JSON.stringify(item) : item}</li>`).join("");
    return `<div class="result-summary"><p>Updated ${data.length} record(s).</p><ul>${preview}</ul></div>`;
  }

  if (typeof data === "object") {
    const rows = Object.entries(data)
      .map(([key, value]) => {
        let rendered = value;
        if (typeof value === "object" && value !== null) rendered = JSON.stringify(value);
        if (rendered === "" || rendered === null || rendered === undefined) rendered = "-";
        return `<dt>${key.replace(/_/g, " ")}</dt><dd>${rendered}</dd>`;
      })
      .join("");
    return `<dl class="result-kv">${rows}</dl>`;
  }

  return `<p>${String(data)}</p>`;
}

function defaultBuild(action, values) {
  return {
    method: action.method || "POST",
    url: action.url,
    body: values,
  };
}

function isRoleAllowed(item, role) {
  const roles = item?.roles;
  if (!roles || !Array.isArray(roles) || !roles.length) return true;
  return roles.includes(role);
}

async function loadEntityOptions(sourceKey) {
  if (!sourceKey || !ENTITY_SOURCES[sourceKey]) return [];
  if (ENTITY_CACHE[sourceKey]) return ENTITY_CACHE[sourceKey];

  const source = ENTITY_SOURCES[sourceKey];
  const response = await apiRequest(source.url, { method: "GET" });
  const rows = Array.isArray(response.data) ? response.data : [];
  ENTITY_CACHE[sourceKey] = rows;
  return rows;
}

function invalidateEntityCache() {
  Object.keys(ENTITY_CACHE).forEach((key) => delete ENTITY_CACHE[key]);
}

async function hydrateEntitySelects(form, fields, role) {
  if (!form || !Array.isArray(fields)) return;
  for (const field of fields) {
    if (field.type !== "entity-select") continue;
    if (!isRoleAllowed(field, role)) continue;

    const select = form.querySelector(`select[name="${field.name}"]`);
    if (!select) continue;

    const source = ENTITY_SOURCES[field.source];
    if (!source) continue;

    try {
      const rows = await loadEntityOptions(field.source);
      const selected = select.value;
      const firstOption = field.required ? `Select ${field.label}` : "Optional";
      const options = rows
        .map((row) => `<option value="${row[source.valueKey]}">${source.label(row)}</option>`)
        .join("");
      select.innerHTML = `<option value="">${firstOption}</option>${options}`;

      if (selected && select.querySelector(`option[value="${selected}"]`)) {
        select.value = selected;
      } else if (field.autoSelectFirst && rows.length) {
        select.value = String(rows[0][source.valueKey]);
      }
    } catch (_err) {
      select.innerHTML = `<option value="">Options unavailable</option>`;
    }
  }
}

const MODULE_CONFIG = {
  attendance: {
    title: "Attendance",
    actions: [
      {
        key: "attendance-create-session",
        label: "Create Session",
        url: "/api/v1/attendance/sessions",
        method: "POST",
        roles: ["admin", "teacher"],
        fields: [
          {
            name: "class_id",
            label: "Class",
            type: "entity-select",
            source: "classes",
            valueType: "number",
            required: true,
            autoSelectFirst: true,
          },
          { name: "section_id", label: "Section ID", type: "number" },
          {
            name: "subject_id",
            label: "Subject",
            type: "entity-select",
            source: "subjects",
            valueType: "number",
          },
          { name: "session_date", label: "Session Date", type: "date", required: true },
          {
            name: "source",
            label: "Source",
            type: "select",
            options: [
              { value: "manual", label: "Manual" },
              { value: "ocr", label: "OCR" },
            ],
          },
        ],
      },
      {
        key: "attendance-mark-records",
        label: "Mark Session Records",
        url: "/api/v1/attendance/sessions/:session_id/records",
        method: "POST",
        roles: ["admin", "teacher"],
        fields: [
          {
            name: "session_id",
            label: "Session",
            type: "entity-select",
            source: "attendance_sessions",
            valueType: "number",
            required: true,
          },
          {
            name: "student_id",
            label: "Student",
            type: "entity-select",
            source: "students",
            valueType: "number",
            required: true,
          },
          {
            name: "status",
            label: "Status",
            type: "select",
            options: [
              { value: "present", label: "Present" },
              { value: "absent", label: "Absent" },
              { value: "late", label: "Late" },
            ],
          },
          { name: "remarks", label: "Remarks", type: "text" },
        ],
        build(values) {
          return {
            method: "POST",
            url: `/api/v1/attendance/sessions/${values.session_id}/records`,
            body: {
              records: [
                {
                  student_id: values.student_id,
                  status: values.status || "present",
                  remarks: values.remarks || "",
                },
              ],
            },
          };
        },
      },
      {
        key: "attendance-teacher-self",
        label: "Teacher Self Attendance",
        url: "/api/v1/attendance/teacher-self",
        method: "POST",
        roles: ["admin", "teacher"],
        fields: [
          { name: "attendance_date", label: "Date", type: "date", required: true },
          {
            name: "status",
            label: "Status",
            type: "select",
            options: [
              { value: "present", label: "Present" },
              { value: "absent", label: "Absent" },
            ],
          },
        ],
      },
      {
        key: "attendance-ocr-import-manual",
        label: "OCR Import (Manual Lines)",
        url: "/api/v1/attendance/ocr/import",
        method: "POST",
        roles: ["admin", "teacher"],
        fields: [
          {
            name: "lines_blob",
            label: "OCR Lines",
            type: "textarea",
            required: true,
            help: "Paste one student attendance line per row",
          },
        ],
        build(values) {
          return {
            method: "POST",
            url: "/api/v1/attendance/ocr/import",
            body: {
              lines: String(values.lines_blob || "")
                .split("\n")
                .map((x) => x.trim())
                .filter(Boolean),
            },
          };
        },
      },
      {
        key: "attendance-ocr-commit-line",
        label: "OCR Map + Commit",
        url: "/api/v1/attendance/ocr/batches/:batch_id/commit",
        method: "POST",
        roles: ["admin", "teacher"],
        fields: [
          {
            name: "batch_id",
            label: "OCR Batch",
            type: "entity-select",
            source: "ocr_batches",
            valueType: "number",
            required: true,
          },
          {
            name: "session_id",
            label: "Session",
            type: "entity-select",
            source: "attendance_sessions",
            valueType: "number",
            required: true,
          },
          { name: "line_id", label: "Line ID", type: "number", required: true },
          {
            name: "student_id",
            label: "Student",
            type: "entity-select",
            source: "students",
            valueType: "number",
            required: true,
          },
          {
            name: "status",
            label: "Status",
            type: "select",
            options: [
              { value: "present", label: "Present" },
              { value: "absent", label: "Absent" },
              { value: "late", label: "Late" },
            ],
          },
        ],
        build(values) {
          return {
            method: "POST",
            url: `/api/v1/attendance/ocr/batches/${values.batch_id}/commit`,
            body: {
              session_id: values.session_id,
              mappings: [
                {
                  line_id: values.line_id,
                  student_id: values.student_id,
                  status: values.status || "present",
                },
              ],
            },
          };
        },
      },
      {
        key: "attendance-student-summary",
        label: "Student Attendance Summary",
        url: "/api/v1/attendance/students/:student_id/summary",
        method: "GET",
        roles: ["admin", "teacher"],
        fields: [
          {
            name: "student_id",
            label: "Student",
            type: "entity-select",
            source: "students",
            valueType: "number",
            required: true,
          },
        ],
        build(values) {
          return { method: "GET", url: `/api/v1/attendance/students/${values.student_id}/summary` };
        },
      },
      {
        key: "attendance-my-summary",
        label: "My Attendance Summary",
        url: "/api/v1/attendance/my-summary",
        method: "GET",
        roles: ["parent", "student"],
        fields: [],
        build() {
          return { method: "GET", url: "/api/v1/attendance/my-summary" };
        },
      },
    ],
    lists: [
      {
        key: "attendance-sessions",
        label: "Attendance Sessions",
        url: "/api/v1/attendance/sessions",
        roles: ["admin", "teacher"],
        columns: [
          { key: "id", label: "ID" },
          { key: "class_id", label: "Class" },
          { key: "section_id", label: "Section" },
          { key: "subject_id", label: "Subject" },
          { key: "session_date", label: "Date" },
          { key: "source", label: "Source" },
        ],
      },
      {
        key: "attendance-records",
        label: "Attendance Records",
        url: "/api/v1/attendance/reports",
        roles: ["admin", "teacher"],
        columns: [
          { key: "id", label: "ID" },
          { key: "session_id", label: "Session" },
          { key: "student_id", label: "Student" },
          { key: "status", label: "Status" },
          { key: "session_date", label: "Date" },
        ],
      },
      {
        key: "attendance-ocr-batches",
        label: "OCR Batches",
        url: "/api/v1/attendance/ocr/batches",
        roles: ["admin", "teacher"],
        columns: [
          { key: "id", label: "ID" },
          { key: "uploaded_by", label: "Uploaded By" },
          { key: "parse_status", label: "Status" },
          { key: "line_count", label: "Lines" },
          { key: "created_at", label: "Created" },
        ],
      },
      {
        key: "teacher-self-log",
        label: "Teacher Attendance Log",
        url: "/api/v1/attendance/teacher-self",
        roles: ["admin", "teacher"],
        columns: [
          { key: "id", label: "ID" },
          { key: "teacher_user_id", label: "Teacher" },
          { key: "attendance_date", label: "Date" },
          { key: "status", label: "Status" },
        ],
      },
      {
        key: "my-attendance-summary-list",
        label: "My Attendance Summary",
        url: "/api/v1/attendance/my-summary",
        roles: ["parent", "student"],
        columns: [
          { key: "student_id", label: "Student ID" },
          { key: "student_name", label: "Student Name" },
          { key: "totals", label: "Totals" },
        ],
      },
      {
        key: "my-attendance-records-list",
        label: "My Attendance Records",
        url: "/api/v1/attendance/my-records",
        roles: ["parent", "student"],
        columns: [
          { key: "id", label: "ID" },
          { key: "student_name", label: "Student" },
          { key: "session_date", label: "Date" },
          { key: "status", label: "Status" },
          { key: "remarks", label: "Remarks" },
        ],
      },
    ],
  },
  exams: {
    title: "Exams",
    actions: [
      {
        key: "exam-create",
        label: "Create Exam",
        url: "/api/v1/exams",
        method: "POST",
        roles: ["admin", "teacher"],
        fields: [
          { name: "name", label: "Exam Name", type: "text", required: true },
          {
            name: "class_id",
            label: "Class",
            type: "entity-select",
            source: "classes",
            valueType: "number",
            required: true,
            autoSelectFirst: true,
          },
        ],
      },
      {
        key: "exam-schedule",
        label: "Schedule Exam",
        url: "/api/v1/exams/:exam_id/schedule",
        method: "POST",
        roles: ["admin", "teacher"],
        fields: [
          {
            name: "exam_id",
            label: "Exam",
            type: "entity-select",
            source: "exams",
            valueType: "number",
            required: true,
          },
          { name: "scheduled_from", label: "Start", type: "date", required: true },
          { name: "scheduled_to", label: "End", type: "date", required: true },
        ],
        build(values) {
          return {
            method: "POST",
            url: `/api/v1/exams/${values.exam_id}/schedule`,
            body: { scheduled_from: values.scheduled_from, scheduled_to: values.scheduled_to },
          };
        },
      },
      {
        key: "exam-marks",
        label: "Add Marks",
        url: "/api/v1/exams/:exam_id/marks",
        method: "POST",
        roles: ["admin", "teacher"],
        fields: [
          {
            name: "exam_id",
            label: "Exam",
            type: "entity-select",
            source: "exams",
            valueType: "number",
            required: true,
          },
          {
            name: "subject_id",
            label: "Subject",
            type: "entity-select",
            source: "subjects",
            valueType: "number",
            required: true,
          },
          {
            name: "student_id",
            label: "Student",
            type: "entity-select",
            source: "students",
            valueType: "number",
            required: true,
          },
          { name: "marks_obtained", label: "Marks", type: "number", required: true },
          { name: "grade", label: "Grade", type: "text" },
        ],
        build(values) {
          return {
            method: "POST",
            url: `/api/v1/exams/${values.exam_id}/marks`,
            body: {
              subject_id: values.subject_id,
              entries: [
                {
                  student_id: values.student_id,
                  marks_obtained: values.marks_obtained,
                  grade: values.grade || null,
                },
              ],
            },
          };
        },
      },
      {
        key: "exam-publish",
        label: "Publish Exam",
        url: "/api/v1/exams/:exam_id/publish",
        method: "POST",
        roles: ["admin", "teacher"],
        fields: [
          {
            name: "exam_id",
            label: "Exam",
            type: "entity-select",
            source: "exams",
            valueType: "number",
            required: true,
          },
        ],
        build(values) {
          return {
            method: "POST",
            url: `/api/v1/exams/${values.exam_id}/publish`,
            body: {},
          };
        },
      },
      {
        key: "exam-overview",
        label: "Exam Overview",
        url: "/api/v1/exams/:exam_id/overview",
        method: "GET",
        roles: ["admin", "teacher", "parent", "student"],
        fields: [
          {
            name: "exam_id",
            label: "Exam",
            type: "entity-select",
            source: "exams",
            valueType: "number",
            required: true,
          },
        ],
        build(values) {
          return { method: "GET", url: `/api/v1/exams/${values.exam_id}/overview` };
        },
      },
      {
        key: "exam-view-marks",
        label: "View Exam Marks",
        url: "/api/v1/exams/:exam_id/marks",
        method: "GET",
        roles: ["admin", "teacher", "parent", "student"],
        fields: [
          {
            name: "exam_id",
            label: "Exam",
            type: "entity-select",
            source: "exams",
            valueType: "number",
            required: true,
          },
          {
            name: "student_id",
            label: "Student (Optional)",
            type: "entity-select",
            source: "students",
            valueType: "number",
          },
        ],
        build(values) {
          const query = values.student_id ? `?student_id=${values.student_id}` : "";
          return { method: "GET", url: `/api/v1/exams/${values.exam_id}/marks${query}` };
        },
      },
      {
        key: "exam-my-results",
        label: "My Results",
        url: "/api/v1/exams/my-results",
        method: "GET",
        roles: ["parent", "student"],
        fields: [],
        build() {
          return { method: "GET", url: "/api/v1/exams/my-results" };
        },
      },
    ],
    lists: [
      {
        key: "exam-list",
        label: "Exam List",
        url: "/api/v1/exams",
        roles: ["admin", "teacher", "parent", "student"],
        columns: [
          { key: "id", label: "ID" },
          { key: "name", label: "Name" },
          { key: "class_id", label: "Class" },
          { key: "status", label: "Status" },
          { key: "scheduled_from", label: "From" },
          { key: "scheduled_to", label: "To" },
        ],
      },
      {
        key: "my-results-list",
        label: "My Results",
        url: "/api/v1/exams/my-results",
        roles: ["parent", "student"],
        columns: [
          { key: "report_card_id", label: "Report Card" },
          { key: "student_name", label: "Student" },
          { key: "exam_name", label: "Exam" },
          { key: "percentage", label: "Percentage" },
          { key: "status", label: "Status" },
        ],
      },
    ],
  },
  report_cards: {
    title: "Report Cards",
    actions: [
      {
        key: "report-fetch",
        label: "Fetch Report Card",
        url: "/api/v1/report-cards/:student_id",
        method: "GET",
        roles: ["admin", "teacher"],
        fields: [
          {
            name: "student_id",
            label: "Student",
            type: "entity-select",
            source: "students",
            valueType: "number",
            required: true,
          },
        ],
        build(values) {
          return { method: "GET", url: `/api/v1/report-cards/${values.student_id}` };
        },
        resultAsHtml: true,
        onResult(result) {
          const card = result?.data;
          if (!card) return "<p>No report card found.</p>";
          const rows = (card.items || [])
            .map((x) => `<tr><td>${x.subject}</td><td>${x.marks_obtained}</td><td>${x.max_marks}</td><td>${x.grade || "-"}</td></tr>`)
            .join("");
          return `
            <div class="report-card-preview">
              <h4>Report Card #${card.id} (Exam ${card.exam_id})</h4>
              <p>Total: <strong>${card.total_marks}</strong> | Percentage: <strong>${card.percentage}%</strong></p>
              <table class="erp-table">
                <thead><tr><th>Subject</th><th>Marks</th><th>Max</th><th>Grade</th></tr></thead>
                <tbody>${rows || "<tr><td colspan='4'>No rows</td></tr>"}</tbody>
              </table>
              <p><a class="btn btn-small" href="/api/v1/report-cards/${card.student_id}/pdf" target="_blank" rel="noopener">Download PDF</a></p>
            </div>
          `;
        },
      },
      {
        key: "report-list",
        label: "List Report Cards",
        url: "/api/v1/report-cards",
        method: "GET",
        roles: ["admin", "teacher", "parent", "student"],
        fields: [
          {
            name: "exam_id",
            label: "Exam (Optional)",
            type: "entity-select",
            source: "exams",
            valueType: "number",
          },
          {
            name: "student_id",
            label: "Student (Optional)",
            type: "entity-select",
            source: "students",
            valueType: "number",
          },
        ],
        build(values) {
          const params = new URLSearchParams();
          if (values.exam_id) params.set("exam_id", values.exam_id);
          if (values.student_id) params.set("student_id", values.student_id);
          const query = params.toString() ? `?${params.toString()}` : "";
          return { method: "GET", url: `/api/v1/report-cards${query}` };
        },
      },
    ],
    lists: [
      {
        key: "report-cards-list",
        label: "Recent Report Cards",
        url: "/api/v1/report-cards",
        roles: ["admin", "teacher", "parent", "student"],
        columns: [
          { key: "id", label: "ID" },
          { key: "student_name", label: "Student" },
          { key: "exam_name", label: "Exam" },
          { key: "percentage", label: "Percentage" },
          { key: "status", label: "Status" },
        ],
      },
    ],
  },
  fees: {
    title: "Fees",
    actions: [
      {
        key: "fees-structure",
        label: "Create Fee Structure",
        url: "/api/v1/fees/structures",
        method: "POST",
        fields: [
          { name: "class_id", label: "Class ID", type: "number", required: true },
          { name: "title", label: "Title", type: "text", required: true },
          { name: "total_amount", label: "Total Amount", type: "number", required: true },
        ],
      },
      {
        key: "fees-installment",
        label: "Create Installment",
        url: "/api/v1/fees/installments",
        method: "POST",
        fields: [
          { name: "structure_id", label: "Structure ID", type: "number", required: true },
          { name: "title", label: "Title", type: "text", required: true },
          { name: "amount", label: "Amount", type: "number", required: true },
          { name: "due_date", label: "Due Date", type: "date", required: true },
        ],
      },
      {
        key: "fees-receipt",
        label: "Post Receipt",
        url: "/api/v1/fees/receipts",
        method: "POST",
        fields: [
          { name: "ledger_id", label: "Ledger ID", type: "number", required: true },
          { name: "amount", label: "Amount", type: "number", required: true },
          { name: "payment_mode", label: "Payment Mode", type: "text", placeholder: "cash" },
          { name: "reference_no", label: "Reference", type: "text" },
        ],
      },
      {
        key: "fees-dues",
        label: "Check Student Dues",
        url: "/api/v1/fees/:student_id/dues",
        method: "GET",
        fields: [{ name: "student_id", label: "Student ID", type: "number", required: true }],
        build(values) {
          return { method: "GET", url: `/api/v1/fees/${values.student_id}/dues` };
        },
      },
    ],
    lists: [
      {
        key: "fee-structures-list",
        label: "Fee Structures",
        url: "/api/v1/fees/structures",
        columns: [
          { key: "id", label: "ID" },
          { key: "class_id", label: "Class" },
          { key: "title", label: "Title" },
          { key: "total_amount", label: "Total" },
        ],
      },
      {
        key: "fee-installments-list",
        label: "Installments",
        url: "/api/v1/fees/installments",
        columns: [
          { key: "id", label: "ID" },
          { key: "structure_id", label: "Structure" },
          { key: "title", label: "Title" },
          { key: "amount", label: "Amount" },
          { key: "due_date", label: "Due Date" },
        ],
      },
    ],
  },
  notices: {
    title: "Notice Board",
    actions: [
      {
        key: "notice-create",
        label: "Create Notice",
        url: "/api/v1/notices",
        method: "POST",
        fields: [
          { name: "title", label: "Title", type: "text", required: true },
          { name: "body", label: "Body", type: "textarea", required: true },
          { name: "audience", label: "Audience", type: "text", placeholder: "all" },
        ],
      },
    ],
    lists: [
      {
        key: "notices-list",
        label: "Notices",
        url: "/api/v1/notices",
        columns: [
          { key: "id", label: "ID" },
          { key: "title", label: "Title" },
          { key: "audience", label: "Audience" },
          { key: "created_at", label: "Created" },
        ],
      },
    ],
  },
  events: {
    title: "Events",
    actions: [
      {
        key: "event-create",
        label: "Create Event",
        url: "/api/v1/events",
        method: "POST",
        fields: [
          { name: "title", label: "Title", type: "text", required: true },
          { name: "details", label: "Details", type: "textarea" },
          { name: "starts_at", label: "Starts", type: "datetime", required: true },
          { name: "ends_at", label: "Ends", type: "datetime" },
          { name: "event_type", label: "Type", type: "text", placeholder: "school" },
        ],
      },
    ],
    lists: [
      {
        key: "events-list",
        label: "Events",
        url: "/api/v1/events",
        columns: [
          { key: "id", label: "ID" },
          { key: "title", label: "Title" },
          { key: "event_type", label: "Type" },
          { key: "starts_at", label: "Starts" },
          { key: "ends_at", label: "Ends" },
        ],
      },
    ],
  },
  reminders: {
    title: "Reminders",
    actions: [
      {
        key: "reminder-create",
        label: "Create Reminder",
        url: "/api/v1/reminders",
        method: "POST",
        fields: [
          { name: "title", label: "Title", type: "text", required: true },
          { name: "content", label: "Content", type: "textarea" },
          { name: "remind_at", label: "Remind At", type: "datetime", required: true },
        ],
      },
    ],
    lists: [
      {
        key: "reminders-list",
        label: "Reminders",
        url: "/api/v1/reminders",
        columns: [
          { key: "id", label: "ID" },
          { key: "title", label: "Title" },
          { key: "remind_at", label: "Remind At" },
          { key: "created_by", label: "Created By" },
        ],
      },
    ],
  },
  messaging: {
    title: "Messaging",
    actions: [
      {
        key: "message-thread-create",
        label: "Create Thread",
        url: "/api/v1/messages/threads",
        method: "POST",
        fields: [
          {
            name: "thread_type",
            label: "Thread Type",
            type: "select",
            options: [
              { value: "dm", label: "DM" },
              { value: "group", label: "Group" },
              { value: "class", label: "Class" },
            ],
          },
          { name: "title", label: "Title", type: "text" },
          {
            name: "member_ids",
            label: "Member IDs",
            type: "text",
            valueType: "csv-int",
            help: "Comma-separated user IDs, e.g. 2,3,4",
            required: true,
          },
        ],
      },
      {
        key: "message-send",
        label: "Send Message",
        url: "/api/v1/messages/threads/:thread_id/messages",
        method: "POST",
        fields: [
          { name: "thread_id", label: "Thread ID", type: "number", required: true },
          { name: "body", label: "Message", type: "textarea", required: true },
        ],
        build(values) {
          return {
            method: "POST",
            url: `/api/v1/messages/threads/${values.thread_id}/messages`,
            body: { body: values.body },
          };
        },
      },
      {
        key: "message-fetch",
        label: "Fetch Thread Messages",
        url: "/api/v1/messages/threads/:thread_id/messages",
        method: "GET",
        fields: [{ name: "thread_id", label: "Thread ID", type: "number", required: true }],
        build(values) {
          return {
            method: "GET",
            url: `/api/v1/messages/threads/${values.thread_id}/messages`,
          };
        },
      },
    ],
    lists: [
      {
        key: "thread-list",
        label: "My Threads",
        url: "/api/v1/messages/threads",
        columns: [
          { key: "id", label: "ID" },
          { key: "title", label: "Title" },
          { key: "thread_type", label: "Type" },
          { key: "created_by", label: "By" },
          { key: "updated_at", label: "Updated" },
        ],
      },
    ],
  },
  calendar: {
    title: "Calendar",
    lists: [
      {
        key: "calendar-list",
        label: "Calendar Entries",
        url: "/api/v1/calendar",
        columns: [
          { key: "id", label: "ID" },
          { key: "title", label: "Title" },
          { key: "entry_type", label: "Type" },
          { key: "starts_at", label: "Starts" },
          { key: "ends_at", label: "Ends" },
        ],
      },
    ],
  },
  admissions: {
    title: "Admissions",
    actions: [
      {
        key: "admission-create",
        label: "Create Admission Form",
        url: "/api/v1/admissions/forms",
        method: "POST",
        fields: [
          { name: "student_name", label: "Student Name", type: "text", required: true },
          { name: "guardian_name", label: "Guardian Name", type: "text", required: true },
          { name: "target_class", label: "Target Class", type: "text", required: true },
        ],
      },
      {
        key: "admission-status",
        label: "Update Status",
        url: "/api/v1/admissions/forms/:form_id/status",
        method: "PATCH",
        fields: [
          { name: "form_id", label: "Form ID", type: "number", required: true },
          { name: "status", label: "Status", type: "text", required: true },
        ],
        build(values) {
          return {
            method: "PATCH",
            url: `/api/v1/admissions/forms/${values.form_id}/status`,
            body: { status: values.status },
          };
        },
      },
    ],
    lists: [
      {
        key: "admissions-list",
        label: "Admission Forms",
        url: "/api/v1/admissions/forms",
        columns: [
          { key: "id", label: "ID" },
          { key: "student_name", label: "Student" },
          { key: "guardian_name", label: "Guardian" },
          { key: "target_class", label: "Target Class" },
          { key: "status", label: "Status" },
        ],
      },
    ],
  },
  transport: {
    title: "Transport",
    actions: [
      {
        key: "transport-route",
        label: "Create Route",
        url: "/api/v1/transport/routes",
        method: "POST",
        fields: [
          { name: "name", label: "Route Name", type: "text", required: true },
          { name: "shift", label: "Shift", type: "text", placeholder: "morning" },
        ],
      },
      {
        key: "transport-vehicle",
        label: "Create Vehicle",
        url: "/api/v1/transport/vehicles",
        method: "POST",
        fields: [
          { name: "registration_no", label: "Registration No", type: "text", required: true },
          { name: "capacity", label: "Capacity", type: "number" },
        ],
      },
      {
        key: "transport-stop",
        label: "Create Stop",
        url: "/api/v1/transport/stops",
        method: "POST",
        fields: [
          { name: "route_id", label: "Route ID", type: "number", required: true },
          { name: "stop_name", label: "Stop Name", type: "text", required: true },
          { name: "stop_order", label: "Order", type: "number", required: true },
        ],
      },
    ],
    lists: [
      {
        key: "transport-routes-list",
        label: "Routes",
        url: "/api/v1/transport/routes",
        columns: [
          { key: "id", label: "ID" },
          { key: "name", label: "Name" },
          { key: "shift", label: "Shift" },
        ],
      },
      {
        key: "transport-vehicles-list",
        label: "Vehicles",
        url: "/api/v1/transport/vehicles",
        columns: [
          { key: "id", label: "ID" },
          { key: "registration_no", label: "Registration" },
          { key: "capacity", label: "Capacity" },
        ],
      },
      {
        key: "transport-stops-list",
        label: "Stops",
        url: "/api/v1/transport/stops",
        columns: [
          { key: "id", label: "ID" },
          { key: "route_id", label: "Route" },
          { key: "stop_name", label: "Stop" },
          { key: "stop_order", label: "Order" },
        ],
      },
    ],
  },
  payroll: {
    title: "Payroll",
    actions: [
      {
        key: "payroll-cycle",
        label: "Create Payroll Cycle",
        url: "/api/v1/payroll/cycles",
        method: "POST",
        fields: [
          { name: "month_label", label: "Month Label", type: "text", required: true, placeholder: "2026-02" },
          { name: "status", label: "Status", type: "text", placeholder: "draft" },
        ],
      },
      {
        key: "payroll-entry",
        label: "Create Payroll Entry",
        url: "/api/v1/payroll/entries",
        method: "POST",
        fields: [
          { name: "cycle_id", label: "Cycle ID", type: "number", required: true },
          { name: "teacher_user_id", label: "Teacher User ID", type: "number", required: true },
          { name: "gross_pay", label: "Gross Pay", type: "number", required: true },
          { name: "net_pay", label: "Net Pay", type: "number", required: true },
        ],
      },
    ],
    lists: [
      {
        key: "payroll-cycle-list",
        label: "Payroll Cycles",
        url: "/api/v1/payroll/cycles",
        columns: [
          { key: "id", label: "ID" },
          { key: "month_label", label: "Month" },
          { key: "status", label: "Status" },
        ],
      },
      {
        key: "payroll-entry-list",
        label: "Payroll Entries",
        url: "/api/v1/payroll/entries",
        columns: [
          { key: "id", label: "ID" },
          { key: "cycle_id", label: "Cycle" },
          { key: "teacher_user_id", label: "Teacher" },
          { key: "gross_pay", label: "Gross" },
          { key: "net_pay", label: "Net" },
        ],
      },
    ],
  },
  library: {
    title: "Library",
    actions: [
      {
        key: "library-book",
        label: "Create Book",
        url: "/api/v1/library/books",
        method: "POST",
        fields: [
          { name: "title", label: "Title", type: "text", required: true },
          { name: "author", label: "Author", type: "text", required: true },
          { name: "isbn", label: "ISBN", type: "text" },
        ],
      },
      {
        key: "library-loan",
        label: "Create Loan",
        url: "/api/v1/library/loans",
        method: "POST",
        fields: [
          { name: "copy_id", label: "Copy ID", type: "number", required: true },
          { name: "borrower_user_id", label: "Borrower User ID", type: "number", required: true },
          { name: "due_date", label: "Due Date", type: "date", required: true },
        ],
      },
    ],
    lists: [
      {
        key: "library-book-list",
        label: "Books",
        url: "/api/v1/library/books",
        columns: [
          { key: "id", label: "ID" },
          { key: "title", label: "Title" },
          { key: "author", label: "Author" },
          { key: "isbn", label: "ISBN" },
        ],
      },
      {
        key: "library-loan-list",
        label: "Loans",
        url: "/api/v1/library/loans",
        columns: [
          { key: "id", label: "ID" },
          { key: "copy_id", label: "Copy" },
          { key: "borrower_user_id", label: "Borrower" },
          { key: "due_date", label: "Due" },
          { key: "returned_at", label: "Returned" },
        ],
      },
    ],
  },
  hostel: {
    title: "Hostel",
    actions: [
      {
        key: "hostel-create",
        label: "Create Hostel",
        url: "/api/v1/hostel/hostels",
        method: "POST",
        fields: [{ name: "name", label: "Hostel Name", type: "text", required: true }],
      },
      {
        key: "room-create",
        label: "Create Room",
        url: "/api/v1/hostel/rooms",
        method: "POST",
        fields: [
          { name: "hostel_id", label: "Hostel ID", type: "number", required: true },
          { name: "room_no", label: "Room No", type: "text", required: true },
          { name: "capacity", label: "Capacity", type: "number" },
        ],
      },
    ],
    lists: [
      {
        key: "hostel-list",
        label: "Hostels",
        url: "/api/v1/hostel/hostels",
        columns: [
          { key: "id", label: "ID" },
          { key: "name", label: "Name" },
        ],
      },
      {
        key: "room-list",
        label: "Rooms",
        url: "/api/v1/hostel/rooms",
        columns: [
          { key: "id", label: "ID" },
          { key: "hostel_id", label: "Hostel" },
          { key: "room_no", label: "Room" },
          { key: "capacity", label: "Capacity" },
        ],
      },
    ],
  },
  inventory: {
    title: "Inventory",
    actions: [
      {
        key: "inventory-item",
        label: "Create Item",
        url: "/api/v1/inventory/items",
        method: "POST",
        fields: [
          { name: "name", label: "Item Name", type: "text", required: true },
          { name: "sku", label: "SKU", type: "text" },
          { name: "quantity", label: "Quantity", type: "number" },
        ],
      },
      {
        key: "inventory-move",
        label: "Record Stock Move",
        url: "/api/v1/inventory/stock-moves",
        method: "POST",
        fields: [
          { name: "item_id", label: "Item ID", type: "number", required: true },
          { name: "move_type", label: "Move Type", type: "text", required: true, placeholder: "in/out" },
          { name: "quantity", label: "Quantity", type: "number", required: true },
          { name: "notes", label: "Notes", type: "text" },
        ],
      },
    ],
    lists: [
      {
        key: "inventory-item-list",
        label: "Items",
        url: "/api/v1/inventory/items",
        columns: [
          { key: "id", label: "ID" },
          { key: "name", label: "Name" },
          { key: "sku", label: "SKU" },
          { key: "quantity", label: "Qty" },
        ],
      },
      {
        key: "inventory-move-list",
        label: "Stock Moves",
        url: "/api/v1/inventory/stock-moves",
        columns: [
          { key: "id", label: "ID" },
          { key: "item_id", label: "Item" },
          { key: "move_type", label: "Type" },
          { key: "quantity", label: "Qty" },
          { key: "notes", label: "Notes" },
        ],
      },
    ],
  },
  coaching: {
    title: "Coaching",
    actions: [
      {
        key: "coaching-course",
        label: "Create Course",
        url: "/api/v1/coaching/courses",
        method: "POST",
        fields: [
          { name: "code", label: "Code", type: "text", required: true },
          { name: "title", label: "Title", type: "text", required: true },
        ],
      },
      {
        key: "coaching-batch",
        label: "Create Batch",
        url: "/api/v1/coaching/batches",
        method: "POST",
        fields: [
          { name: "course_id", label: "Course ID", type: "number", required: true },
          { name: "name", label: "Batch Name", type: "text", required: true },
          { name: "timing", label: "Timing", type: "text" },
        ],
      },
      {
        key: "coaching-series",
        label: "Create Test Series",
        url: "/api/v1/coaching/test-series",
        method: "POST",
        fields: [
          { name: "batch_id", label: "Batch ID", type: "number", required: true },
          { name: "title", label: "Title", type: "text", required: true },
          { name: "total_marks", label: "Total Marks", type: "number" },
        ],
      },
      {
        key: "coaching-attempt",
        label: "Create Test Attempt",
        url: "/api/v1/coaching/test-attempts",
        method: "POST",
        fields: [
          { name: "test_series_id", label: "Test Series ID", type: "number", required: true },
          { name: "student_id", label: "Student ID", type: "number", required: true },
          { name: "score", label: "Score", type: "number", required: true },
        ],
      },
    ],
    lists: [
      {
        key: "coaching-course-list",
        label: "Courses",
        url: "/api/v1/coaching/courses",
        columns: [
          { key: "id", label: "ID" },
          { key: "code", label: "Code" },
          { key: "title", label: "Title" },
        ],
      },
      {
        key: "coaching-batch-list",
        label: "Batches",
        url: "/api/v1/coaching/batches",
        columns: [
          { key: "id", label: "ID" },
          { key: "course_id", label: "Course" },
          { key: "name", label: "Name" },
          { key: "timing", label: "Timing" },
        ],
      },
      {
        key: "coaching-series-list",
        label: "Test Series",
        url: "/api/v1/coaching/test-series",
        columns: [
          { key: "id", label: "ID" },
          { key: "batch_id", label: "Batch" },
          { key: "title", label: "Title" },
          { key: "total_marks", label: "Total" },
        ],
      },
      {
        key: "coaching-attempt-list",
        label: "Test Attempts",
        url: "/api/v1/coaching/test-attempts",
        columns: [
          { key: "id", label: "ID" },
          { key: "test_series_id", label: "Series" },
          { key: "student_id", label: "Student" },
          { key: "score", label: "Score" },
        ],
      },
    ],
  },
};

function createActionCard(action, moduleKey, refreshLists, resultPanel, role) {
  const fieldsHtml = (action.fields || []).map((field) => fieldTemplate(action.key, field)).join("");
  const wrapper = document.createElement("section");
  wrapper.className = "action-card board-card board-blue";
  wrapper.innerHTML = `
    <h3>${action.label}</h3>
    <form class="module-form" data-action-key="${action.key}">
      <div class="form-grid">${fieldsHtml}</div>
      <button type="submit" class="btn">${action.ctaLabel || "Save"}</button>
    </form>
  `;

  const form = wrapper.querySelector("form");
  hydrateEntitySelects(form, action.fields || [], role);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const values = getFormValues(form, action.fields || []);
      const requestDef = (action.build || defaultBuild)(action, values, moduleKey);

      const options = { method: requestDef.method || "POST" };
      if (requestDef.method !== "GET") {
        options.body = JSON.stringify(requestDef.body || {});
      }

      const response = await apiRequest(requestDef.url, options);
      const resultHtml = action.onResult ? action.onResult(response) : renderResultData(response.data);
      if (action.resultAsHtml) {
        resultPanel.innerHTML = `<h3>Activity Update</h3><div class="alert alert-success">${action.label} completed successfully.</div>${resultHtml}`;
      } else {
        resultPanel.innerHTML = `<h3>Activity Update</h3><div class="alert alert-success">${action.label} completed successfully.</div>${resultHtml}`;
      }
      invalidateEntityCache();
      await refreshLists();
      form.reset();
      hydrateEntitySelects(form, action.fields || [], role);
    } catch (error) {
      resultPanel.innerHTML = `<h3>Activity Update</h3><div class="alert alert-error">${error.message}</div>`;
    }
  });

  return wrapper;
}

function createListCard(listConfig) {
  const wrapper = document.createElement("section");
  wrapper.className = "list-card board-card board-yellow";
  wrapper.innerHTML = `
    <div class="list-card-head">
      <h3>${listConfig.label}</h3>
      <button class="btn btn-small" type="button">Refresh</button>
    </div>
    <div class="list-body"><p>Loading...</p></div>
  `;
  return wrapper;
}

async function initModuleConsole(moduleKey) {
  const root = document.getElementById("module-console");
  if (!root) return;
  const role = (root.dataset.role || "student").toLowerCase();

  const config = MODULE_CONFIG[moduleKey];
  if (!config) {
    root.innerHTML = "<p>This workspace is being configured for your role.</p>";
    return;
  }

  const actionContainer = document.createElement("div");
  actionContainer.className = "module-actions";

  const listContainer = document.createElement("div");
  listContainer.className = "module-lists";

  const resultPanel = document.createElement("section");
  resultPanel.className = "result-panel board-card board-green";
  resultPanel.innerHTML = "<h3>Activity Update</h3><p>Complete a workflow to see the latest update.</p>";

  root.innerHTML = "";
  root.appendChild(actionContainer);
  root.appendChild(listContainer);
  root.appendChild(resultPanel);

  const allowedActions = (config.actions || []).filter((action) => isRoleAllowed(action, role));
  const allowedLists = (config.lists || []).filter((listCfg) => isRoleAllowed(listCfg, role));

  const listCards = new Map();
  for (const listCfg of allowedLists) {
    const card = createListCard(listCfg);
    listCards.set(listCfg.key, { config: listCfg, card, body: card.querySelector(".list-body") });
    card.querySelector("button").addEventListener("click", () => fetchList(listCfg, card.querySelector(".list-body")));
    listContainer.appendChild(card);
  }

  async function refreshLists() {
    const tasks = [];
    for (const { config: listCfg, body } of listCards.values()) {
      tasks.push(fetchList(listCfg, body));
    }
    await Promise.all(tasks);
  }

  for (const action of allowedActions) {
    actionContainer.appendChild(createActionCard(action, moduleKey, refreshLists, resultPanel, role));
  }

  if (!allowedActions.length) {
    actionContainer.innerHTML = `<section class="board-card board-blue"><h3>Actions</h3><p>Your role has view-only access in this module.</p></section>`;
  }
  if (!allowedLists.length) {
    listContainer.innerHTML = `<section class="board-card board-yellow"><h3>Records</h3><p>No list views are available for this role.</p></section>`;
  }

  await refreshLists();
}

async function fetchList(listCfg, bodyEl) {
  try {
    const response = await apiRequest(listCfg.url, { method: "GET" });
    const rows = Array.isArray(response.data) ? response.data : [response.data].filter(Boolean);
    bodyEl.innerHTML = objectToTable(rows, listCfg.columns || []);
  } catch (error) {
    bodyEl.innerHTML = `<div class="alert alert-error">${error.message}</div>`;
  }
}

async function loadDashboardLive(role) {
  const noticesEl = document.getElementById("live-notices");
  const eventsEl = document.getElementById("live-events");
  const aiEl = document.getElementById("live-ai-approvals");

  if (noticesEl) {
    try {
      const res = await apiRequest("/api/v1/notices", { method: "GET" });
      const rows = (res.data || []).slice(0, 6);
      noticesEl.innerHTML = rows.length
        ? rows.map((x) => `<li><strong>${x.title}</strong><span>${x.audience}</span></li>`).join("")
        : "<li>No notices</li>";
    } catch (err) {
      noticesEl.innerHTML = `<li>${err.message}</li>`;
    }
  }

  if (eventsEl) {
    try {
      const res = await apiRequest("/api/v1/events", { method: "GET" });
      const rows = (res.data || []).slice(0, 6);
      eventsEl.innerHTML = rows.length
        ? rows.map((x) => `<li><strong>${x.title}</strong><span>${(x.starts_at || "").slice(0, 16)}</span></li>`).join("")
        : "<li>No events</li>";
    } catch (err) {
      eventsEl.innerHTML = `<li>${err.message}</li>`;
    }
  }

  if (aiEl && (role === "admin" || role === "teacher")) {
    try {
      const res = await apiRequest("/api/v1/ai/actions/pending", { method: "GET" });
      const rows = (res.data || []).slice(0, 6);
      aiEl.innerHTML = rows.length
        ? rows
            .map(
              (x) =>
                `<li>
                  <strong>#${x.id}</strong> ${x.action_type}
                  <span class="status status-${x.risk}">${x.risk}</span>
                  <button class="btn btn-small ai-action" data-decision="approve" data-action-id="${x.id}" type="button">Approve</button>
                  <button class="btn btn-small btn-warn ai-action" data-decision="reject" data-action-id="${x.id}" type="button">Reject</button>
                </li>`
            )
            .join("")
        : "<li>No pending approvals</li>";
      wireAiApprovalActions(aiEl, role);
    } catch (err) {
      aiEl.innerHTML = `<li>${err.message}</li>`;
    }
  } else if (aiEl) {
    aiEl.innerHTML = "<li>Visible for admin and teacher roles.</li>";
  }
}

function wireAiApprovalActions(aiEl, role) {
  if (!aiEl || aiEl.dataset.bound === "1") return;
  aiEl.dataset.bound = "1";

  aiEl.addEventListener("click", async (event) => {
    const btn = event.target.closest(".ai-action");
    if (!btn) return;

    const decision = btn.dataset.decision;
    const actionId = btn.dataset.actionId;
    if (!decision || !actionId) return;

    btn.disabled = true;
    try {
      await apiRequest(`/api/v1/ai/actions/${actionId}/${decision}`, {
        method: "POST",
        body: JSON.stringify({ comment: `${role} decision from dashboard` }),
      });
      await loadDashboardLive(role);
    } catch (err) {
      btn.disabled = false;
      alert(err.message);
    }
  });
}

async function erpAskAI() {
  const form = document.getElementById("ai-form");
  const output = document.getElementById("ai-result");
  const chatLog = document.getElementById("ai-chat-log");
  if (!form || !output || !chatLog) return;

  const prompt = form.querySelector("textarea[name='prompt']").value.trim();
  if (!prompt) {
    output.textContent = "Type a prompt first.";
    return;
  }

  appendAiBubble("user", prompt);
  output.textContent = "Thinking...";

  try {
    const json = await apiRequest("/api/v1/ai/chat", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    });
    const data = json?.data || {};
    appendAiBubble("assistant", data.assistant_response || "I could not generate a response right now.");

    if (data.action) {
      const actionText = `Action ${data.action.action_type} is ${data.action.status} (${data.action.risk} risk).`;
      appendAiBubble("assistant", actionText, true);
    }
    output.textContent = "Ready for your next request.";
  } catch (error) {
    appendAiBubble("assistant", `I could not complete that request: ${error.message}`);
    output.textContent = "Please refine your prompt and try again.";
  } finally {
    form.querySelector("textarea[name='prompt']").value = "";
  }
}

function appendAiBubble(role, text, isAction = false) {
  const chatLog = document.getElementById("ai-chat-log");
  if (!chatLog) return;

  const bubble = document.createElement("div");
  bubble.className = `ai-bubble ${role === "user" ? "ai-bubble-user" : "ai-bubble-assistant"}`;
  bubble.textContent = text;

  if (isAction) {
    const chip = document.createElement("span");
    chip.className = "ai-action-chip";
    chip.textContent = "Workflow routing";
    bubble.appendChild(document.createElement("br"));
    bubble.appendChild(chip);
  }

  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
}

document.addEventListener("DOMContentLoaded", () => {
  const moduleEl = document.getElementById("module-console");
  if (moduleEl) {
    initModuleConsole(moduleEl.dataset.moduleKey);
  }

  const dashEl = document.getElementById("dashboard-live");
  if (dashEl) {
    const role = dashEl.dataset.role || "student";
    loadDashboardLive(role);
    setInterval(() => loadDashboardLive(role), 15000);
  }

  const chatLog = document.getElementById("ai-chat-log");
  if (chatLog && !chatLog.dataset.bootstrapped) {
    chatLog.dataset.bootstrapped = "1";
    appendAiBubble(
      "assistant",
      "Hello. I can answer product questions and route supported actions like reminders, notices, and events."
    );
  }
});
