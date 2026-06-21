import os

html_path = 'vyom.html'
if not os.path.exists(html_path):
    print("Error: vyom.html not found!")
    exit(1)

with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

target_start = 12236 # 0-indexed line 12236 is line 12237 (1-based)
target_end = 12370   # lines[target_start:target_end] will include up to index 12369, which is line 12370 (1-based)

print("Verifying range to replace...")
print("Start line (12237):", repr(lines[target_start]))
print("End line (12370):", repr(lines[target_end - 1]))

if "MAIN REPORTS PAGE" not in lines[target_start + 1] or "function ReportsPage" not in lines[target_start + 3]:
    print("Warning: Content mismatch! Expected 'MAIN REPORTS PAGE' and 'function ReportsPage'")
    exit(1)

new_components_and_page = """// ─────────────────────────────────────────────
//  SESSION REPORTS TAB
// ─────────────────────────────────────────────
function SessionReportsTab({ report, sessionCode }) {
  if (!report) return null;
  const students = report.students || [];

  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, marginBottom: 20 } },
      React.createElement('div', { className: 'vc-end-summary-stat-card', style: { padding: 18 } },
        React.createElement('div', { style: { fontSize: '0.9rem', fontWeight: 800, color: 'var(--accent)', marginBottom: 8 } }, '📋 Session Parameters'),
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6, fontSize: '0.82rem', color: 'var(--text)' } },
          React.createElement('div', null, React.createElement('b', null, 'Session Name: '), report.session_name || 'Live Class'),
          React.createElement('div', null, React.createElement('b', null, 'Class Code: '), sessionCode),
          React.createElement('div', null, React.createElement('b', null, 'Created At: '), new Date(report.created_at * 1000).toLocaleString()),
          React.createElement('div', null, React.createElement('b', null, 'Status: '), report.status ? report.status.toUpperCase() : 'WAITING')
        )
      ),
      React.createElement('div', { className: 'vc-end-summary-stat-card', style: { padding: 18 } },
        React.createElement('div', { style: { fontSize: '0.9rem', fontWeight: 800, color: 'var(--accent)', marginBottom: 8 } }, '👥 Attendance Statistics'),
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6, fontSize: '0.82rem', color: 'var(--text)' } },
          React.createElement('div', null, React.createElement('b', null, 'Total Students Joined: '), students.length),
          React.createElement('div', null, React.createElement('b', null, 'Active Participants: '), students.filter(s => s.total_attempts > 0).length),
          React.createElement('div', null, React.createElement('b', null, 'Average Participation: '), `${report.analytics?.participation || 0}%`),
          React.createElement('div', null, React.createElement('b', null, 'Average Understanding: '), `${report.analytics?.understanding || 0}%`)
        )
      )
    ),

    React.createElement('div', { style: { fontSize: '0.9rem', fontWeight: 700, marginBottom: 12 } }, 'Connected Students Roster'),
    React.createElement('div', { className: 'rpt-table-wrapper' },
      React.createElement('table', null,
        React.createElement('thead', null,
          React.createElement('tr', null,
            ['Student Name', 'Student ID', 'Join Time', 'Total Attempted', 'Score (Tasks)', 'Warnings Received'].map(h => 
              React.createElement('th', { key: h }, h)
            )
          )
        ),
        React.createElement('tbody', null,
          students.length === 0 ? React.createElement('tr', null,
            React.createElement('td', { colSpan: 6, style: { padding: '30px', textAlign: 'center', color: 'var(--text3)' } }, 'No students joined this session.')
          ) :
          students.map((s, idx) => {
            const warningsCount = Object.values(s.warnings || {}).reduce((a, b) => a + b, 0);
            return React.createElement('tr', { key: s.student_id, style: { background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' } },
              React.createElement('td', { style: { fontWeight: 700 } }, s.name),
              React.createElement('td', { style: { color: 'var(--text2)', fontFamily: 'monospace' } }, s.student_id),
              React.createElement('td', null, s.joined_at ? new Date(s.joined_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'),
              React.createElement('td', null, s.total_attempts),
              React.createElement('td', { style: { fontWeight: 700 } }, `${s.score} pts`),
              React.createElement('td', { style: { color: warningsCount > 0 ? 'var(--red)' : 'var(--text2)', fontWeight: warningsCount > 0 ? 700 : 500 } }, warningsCount)
            );
          })
        )
      )
    )
  );
}

// ─────────────────────────────────────────────
//  CODING REPORTS TAB
// ─────────────────────────────────────────────
function CodingReportsTab({ sessionCode }) {
  const [codingData, setCodingData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [selectedStudent, setSelectedStudent] = React.useState(null);
  const [uploadingGDrive, setUploadingGDrive] = React.useState(false);
  const [gdriveUrl, setGdriveUrl] = React.useState(null);
  const { add } = React.useContext(AppCtx);

  async function fetchCodingReport() {
    try {
      setLoading(true);
      const data = await apiFetch(`/api/session/${sessionCode}/reports/coding`);
      setCodingData(data);
    } catch (e) {
      add(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    fetchCodingReport();
  }, [sessionCode]);

  if (loading) {
    return React.createElement(RptSkeleton, { rows: 5 });
  }

  if (!codingData || !codingData.has_coding) {
    return React.createElement(RptEmpty, { icon: '💻', title: 'No coding assessment conducted', sub: 'Coding assessment scores and files will appear here once conducted.' });
  }

  const downloadFile = (format) => {
    window.open(`/api/session/${sessionCode}/reports/download?type=coding&format=${format}`, '_blank');
    add(`Downloading coding report as ${format.toUpperCase()}`, 'success');
  };

  const downloadCodeArchive = () => {
    window.open(`/api/session/${sessionCode}/reports/download?type=zip`, '_blank');
    add(`Downloading source code archive (.zip)`, 'success');
  };

  const saveToGDrive = async (format) => {
    try {
      setUploadingGDrive(true);
      setGdriveUrl(null);
      const res = await apiFetch(`/api/session/${sessionCode}/reports/save-gdrive?type=coding&format=${format}`, {
        method: 'POST'
      });
      if (res.success) {
        add("Saved successfully to Google Drive!", "success");
        setGdriveUrl(res.view_url);
      }
    } catch (e) {
      add(e.message || "Upload failed", "error");
    } finally {
      setUploadingGDrive(false);
    }
  };

  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', marginBottom: 16, alignItems: 'center', flexWrap: 'wrap', gap: 12 } },
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: '0.9rem', fontWeight: 700 } }, `Coding assessment: ${codingData.task?.question || 'Untitled Assessment'}`),
        React.createElement('div', { style: { fontSize: '0.78rem', color: 'var(--text3)' } }, `Default Language: ${codingData.task?.language || 'python'}`)
      ),
      React.createElement('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap' } },
        React.createElement('button', { className: 'btn btn-ghost btn-sm', onClick: () => downloadFile('pdf') }, '📄 PDF'),
        React.createElement('button', { className: 'btn btn-ghost btn-sm', onClick: () => downloadFile('excel') }, '📊 Excel'),
        React.createElement('button', { className: 'btn btn-ghost btn-sm', onClick: () => downloadFile('csv') }, '📋 CSV'),
        React.createElement('button', { className: 'btn btn-ghost btn-sm', style: { color: 'var(--accent)' }, onClick: downloadCodeArchive }, '📦 Code ZIP'),
        React.createElement('button', {
          className: `btn btn-primary btn-sm ${uploadingGDrive ? 'loading' : ''}`,
          onClick: () => saveToGDrive('pdf'),
          disabled: uploadingGDrive
        }, '☁️ Save to Drive')
      )
    ),

    gdriveUrl && React.createElement('div', { style: { background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: 8, padding: '10px 14px', marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
      React.createElement('span', { style: { color: '#10b981', fontSize: '0.85rem', fontWeight: 600 } }, '✨ Report saved to Google Drive!'),
      React.createElement('a', { href: gdriveUrl, target: '_blank', rel: 'noopener noreferrer', className: 'btn btn-ghost btn-xs', style: { color: '#10b981', borderColor: 'rgba(16,185,129,0.3)' } }, '🔗 Open File')
    ),

    React.createElement('div', { className: 'rpt-table-wrapper' },
      React.createElement('table', null,
        React.createElement('thead', null,
          React.createElement('tr', null,
            ['Student', 'Passed Test Cases', 'Total Test Cases', 'Score %', 'Language Used', 'Submission Time', 'Actions'].map(h => 
              React.createElement('th', { key: h }, h)
            )
          )
        ),
        React.createElement('tbody', null,
          codingData.report.length === 0 ? React.createElement('tr', null,
            React.createElement('td', { colSpan: 7, style: { padding: '30px', textAlign: 'center', color: 'var(--text3)' } }, 'No student records found.')
          ) :
          codingData.report.map((s, idx) => 
            React.createElement('tr', { key: s.student_id, style: { background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' } },
              React.createElement('td', { style: { fontWeight: 700 } }, s.name),
              React.createElement('td', null, s.passed_cases),
              React.createElement('td', null, s.total_cases),
              React.createElement('td', { style: { fontWeight: 700, color: s.submitted ? 'var(--accent)' : 'var(--text)' } }, `${s.score}%`),
              React.createElement('td', { style: { fontFamily: 'monospace' } }, s.language),
              React.createElement('td', null, s.time),
              React.createElement('td', null,
                s.submitted
                  ? React.createElement('button', { className: 'btn btn-ghost btn-xs', onClick: () => setSelectedStudent(s) }, '💻 View Code')
                  : React.createElement('span', { style: { color: 'var(--text3)', fontSize: '0.78rem' } }, 'Not Submitted')
              )
            )
          )
        )
      )
    ),

    selectedStudent && React.createElement('div', {
      style: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24 }
    },
      React.createElement('div', {
        className: 'card',
        style: { width: '100%', maxWidth: 700, maxHeight: '90vh', display: 'flex', flexDirection: 'column', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '16px', padding: 24 }
      },
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 } },
          React.createElement('div', null,
            React.createElement('h3', { style: { margin: 0, fontSize: '1.2rem', fontWeight: 800 } }, `${selectedStudent.name}'s Submission`),
            React.createElement('div', { style: { fontSize: '0.78rem', color: 'var(--text3)', marginTop: 2 } }, `Language: ${selectedStudent.language} | Score: ${selectedStudent.score}%`)
          ),
          React.createElement('button', { className: 'btn btn-ghost btn-sm', style: { padding: 4, minWidth: 32 }, onClick: () => setSelectedStudent(null) }, '✕')
        ),

        React.createElement('div', { style: { flexGrow: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 } },
          React.createElement('div', null,
            React.createElement('div', { style: { fontSize: '0.8rem', fontWeight: 700, color: 'var(--text2)', marginBottom: 6 } }, '📝 Submitted Source Code:'),
            React.createElement('pre', {
              style: {
                background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 10, padding: 14,
                fontFamily: 'monospace', fontSize: '0.82rem', color: 'var(--text)', overflowX: 'auto', whiteSpace: 'pre-wrap', maxHeight: 220
              }
            }, selectedStudent.code)
          ),

          React.createElement('div', null,
            React.createElement('div', { style: { fontSize: '0.8rem', fontWeight: 700, color: 'var(--text2)', marginBottom: 6 } }, '💻 Stdout Output:'),
            React.createElement('pre', {
              style: {
                background: '#090d16', border: '1px solid var(--border)', borderRadius: 10, padding: 12,
                fontFamily: 'monospace', fontSize: '0.8rem', color: '#10b981', overflowX: 'auto', whiteSpace: 'pre-wrap', minHeight: 40, maxHeight: 100
              }
            }, selectedStudent.output || '— (No stdout output)')
          ),

          selectedStudent.error && React.createElement('div', null,
            React.createElement('div', { style: { fontSize: '0.8rem', fontWeight: 700, color: 'var(--red)', marginBottom: 6 } }, '⚠️ Error Traceback:'),
            React.createElement('pre', {
              style: {
                background: '#1a0505', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 10, padding: 12,
                fontFamily: 'monospace', fontSize: '0.8rem', color: 'var(--red)', overflowX: 'auto', whiteSpace: 'pre-wrap', maxHeight: 100
              }
            }, selectedStudent.error)
          ),

          React.createElement('div', { style: { background: 'rgba(217, 119, 6, 0.04)', border: '1px solid rgba(217, 119, 6, 0.12)', borderRadius: 10, padding: 12 } },
            React.createElement('div', { style: { fontSize: '0.8rem', fontWeight: 700, color: 'var(--accent)', marginBottom: 6 } }, '🎯 Evaluation Outcome:'),
            React.createElement('div', { style: { fontSize: '0.82rem', color: 'var(--text2)' } }, 
              `Passed ${selectedStudent.passed_cases} out of ${selectedStudent.total_cases} test cases successfully.`
            )
          )
        ),

        React.createElement('div', { style: { display: 'flex', justifyContent: 'flex-end', marginTop: 16 } },
          React.createElement('button', { className: 'btn btn-ghost btn-sm', onClick: () => setSelectedStudent(null) }, 'Close Visualizer')
        )
      )
    )
  );
}

// ─────────────────────────────────────────────
//  STUDENT MARKS REGISTER TAB
// ─────────────────────────────────────────────
function StudentMarksRegisterTab({ sessionCode, report }) {
  const [gradebook, setGradebook] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [classFilter, setClassFilter] = React.useState('all');
  const [sortBy, setSortBy] = React.useState('rank');
  const [uploadingGDrive, setUploadingGDrive] = React.useState(false);
  const [gdriveUrl, setGdriveUrl] = React.useState(null);
  const { add } = React.useContext(AppCtx);

  const [currentPage, setCurrentPage] = React.useState(1);
  const itemsPerPage = 10;

  async function fetchGradebook() {
    try {
      setLoading(true);
      const data = await apiFetch(`/api/session/${sessionCode}/reports/gradebook`);
      if (data && data.gradebook) {
        setGradebook(data.gradebook);
      }
    } catch (e) {
      add(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    fetchGradebook();
  }, [sessionCode]);

  if (loading) {
    return React.createElement(RptSkeleton, { rows: 5 });
  }

  let filtered = gradebook.filter(s => 
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.roll_no.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (classFilter !== 'all') {
    filtered = filtered.filter(s => s.class_name === classFilter);
  }

  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === 'name') return a.name.localeCompare(b.name);
    if (sortBy === 'marks') return b.overall_percentage - a.overall_percentage;
    return a.rank - b.rank;
  });

  const uniqueClasses = ['all', ...new Set(gradebook.map(s => s.class_name).filter(Boolean))];

  // Pagination
  const totalItems = sorted.length;
  const totalPages = Math.ceil(totalItems / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedData = sorted.slice(startIndex, startIndex + itemsPerPage);

  const downloadFile = (format) => {
    window.open(`/api/session/${sessionCode}/reports/download?type=gradebook&format=${format}`, '_blank');
    add(`Downloading Gradebook as ${format.toUpperCase()}`, 'success');
  };

  const saveToGDrive = async (format) => {
    try {
      setUploadingGDrive(true);
      setGdriveUrl(null);
      const res = await apiFetch(`/api/session/${sessionCode}/reports/save-gdrive?type=gradebook&format=${format}`, {
        method: 'POST'
      });
      if (res.success) {
        add("Saved successfully to Google Drive!", "success");
        setGdriveUrl(res.view_url);
      }
    } catch (e) {
      add(e.message || "Upload failed", "error");
    } finally {
      setUploadingGDrive(false);
    }
  };

  return React.createElement('div', null,
    // Filters and Actions Row
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' } },
      React.createElement('div', { style: { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' } },
        React.createElement('input', {
          type: 'text',
          className: 'prof-settings-input',
          placeholder: '🔍 Search student or roll...',
          value: searchQuery,
          onChange: (e) => { setSearchQuery(e.target.value); setCurrentPage(1); },
          style: { width: 220 }
        }),
        React.createElement('select', {
          className: 'prof-settings-input',
          value: classFilter,
          onChange: (e) => { setClassFilter(e.target.value); setCurrentPage(1); }
        },
          uniqueClasses.map(c => React.createElement('option', { key: c, value: c }, c === 'all' ? '🏫 All Classes' : c))
        ),
        React.createElement('select', {
          className: 'prof-settings-input',
          value: sortBy,
          onChange: (e) => setSortBy(e.target.value)
        },
          React.createElement('option', { value: 'rank' }, '🏆 Sort by Rank'),
          React.createElement('option', { value: 'marks' }, '📈 Sort by Overall %'),
          React.createElement('option', { value: 'name' }, '🔤 Sort by Name')
        )
      ),
      React.createElement('div', { style: { display: 'flex', gap: 6 } },
        React.createElement('button', { className: 'btn btn-ghost btn-sm', onClick: () => downloadFile('pdf') }, '📄 PDF'),
        React.createElement('button', { className: 'btn btn-ghost btn-sm', onClick: () => downloadFile('excel') }, '📊 Excel'),
        React.createElement('button', { className: 'btn btn-ghost btn-sm', onClick: () => downloadFile('csv') }, '📋 CSV'),
        React.createElement('button', {
          className: `btn btn-primary btn-sm ${uploadingGDrive ? 'loading' : ''}`,
          onClick: () => saveToGDrive('pdf'),
          disabled: uploadingGDrive
        }, '☁️ Save to Drive')
      )
    ),

    gdriveUrl && React.createElement('div', { style: { background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: 8, padding: '10px 14px', marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
      React.createElement('span', { style: { color: '#10b981', fontSize: '0.85rem', fontWeight: 600 } }, '✨ Report saved to Google Drive!'),
      React.createElement('a', { href: gdriveUrl, target: '_blank', rel: 'noopener noreferrer', className: 'btn btn-ghost btn-xs', style: { color: '#10b981', borderColor: 'rgba(16,185,129,0.3)' } }, '🔗 Open File')
    ),

    // Table
    React.createElement('div', { className: 'rpt-table-wrapper' },
      React.createElement('table', null,
        React.createElement('thead', null,
          React.createElement('tr', null,
            ['Rank', 'Student Name', 'Roll No', 'Class', 'Task Score', 'Test Score', 'Coding Score', 'Overall %'].map(h => 
              React.createElement('th', { key: h }, h)
            )
          )
        ),
        React.createElement('tbody', null,
          paginatedData.length === 0 ? React.createElement('tr', null,
            React.createElement('td', { colSpan: 8, style: { padding: '30px', textAlign: 'center', color: 'var(--text3)' } }, 'No student records found.')
          ) :
          paginatedData.map((s, idx) => 
            React.createElement('tr', { key: s.student_id, style: { background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' } },
              React.createElement('td', { style: { fontWeight: 700 } }, `#${s.rank}`),
              React.createElement('td', { style: { fontWeight: 700 } }, s.name),
              React.createElement('td', null, s.roll_no),
              React.createElement('td', null, s.class_name),
              React.createElement('td', null, `${s.task_score}%`),
              React.createElement('td', null, s.test_score !== null ? `${s.test_score}%` : '—'),
              React.createElement('td', null, s.coding_submitted ? `${s.coding_score}%` : '—'),
              React.createElement('td', { style: { fontWeight: 700, color: 'var(--accent)' } }, `${s.overall_percentage}%`)
            )
          )
        )
      )
    ),

    // Pagination controls
    totalPages > 1 && React.createElement('div', { className: 'rpt-pagination' },
      React.createElement('div', { className: 'rpt-pagination-info' },
        `Showing ${startIndex + 1} - ${Math.min(startIndex + itemsPerPage, totalItems)} of ${totalItems} students`
      ),
      React.createElement('div', { className: 'rpt-pagination-btns' },
        React.createElement('button', {
          className: 'btn btn-ghost btn-xs',
          disabled: currentPage === 1,
          onClick: () => setCurrentPage(prev => Math.max(prev - 1, 1))
        }, '◀ Prev'),
        Array.from({ length: totalPages }).map((_, idx) => 
          React.createElement('button', {
            key: idx,
            className: `btn btn-xs ${currentPage === idx + 1 ? 'btn-primary' : 'btn-ghost'}`,
            style: { minWidth: 24 },
            onClick: () => setCurrentPage(idx + 1)
          }, idx + 1)
        ),
        React.createElement('button', {
          className: 'btn btn-ghost btn-xs',
          disabled: currentPage === totalPages,
          onClick: () => setCurrentPage(prev => Math.min(prev + 1, totalPages))
        }, 'Next ▶')
      )
    )
  );
}

// ─────────────────────────────────────────────
//  BULK EXPORT MODAL
// ─────────────────────────────────────────────
function BulkExportModal({ sessionCode, onClose }) {
  const [selectedTypes, setSelectedTypes] = React.useState({
    gradebook: true,
    tasks: true,
    tests: true,
    coding: true
  });
  const [format, setFormat] = React.useState('pdf');
  const [exporting, setExporting] = React.useState(false);
  const [gdriveSaving, setGdriveSaving] = React.useState(false);
  const { add } = React.useContext(AppCtx);

  const toggleType = (key) => {
    setSelectedTypes(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleDownload = async () => {
    const activeKeys = Object.keys(selectedTypes).filter(k => selectedTypes[k]);
    if (activeKeys.length === 0) {
      add("Please select at least one report to export", "error");
      return;
    }

    setExporting(true);
    try {
      for (const key of activeKeys) {
        let downloadType = key;
        if (key === 'tasks') {
          const data = await apiFetch(`/api/session/${sessionCode}/report`);
          const tasks = data.question_stats || [];
          for (const t of tasks) {
            window.open(`/api/session/${sessionCode}/reports/download?type=task&task_id=${t.task_id}&format=${format}`, '_blank');
            await new Promise(r => setTimeout(r, 600));
          }
          continue;
        }

        window.open(`/api/session/${sessionCode}/reports/download?type=${downloadType === 'tests' ? 'test' : downloadType}&format=${format}`, '_blank');
        await new Promise(r => setTimeout(r, 600));
      }
      add("Bulk download triggered successfully!", "success");
      onClose();
    } catch (e) {
      add(e.message || "Bulk export failed", "error");
    } finally {
      setExporting(false);
    }
  };

  const handleSaveToGDrive = async () => {
    const activeKeys = Object.keys(selectedTypes).filter(k => selectedTypes[k]);
    if (activeKeys.length === 0) {
      add("Please select at least one report to save", "error");
      return;
    }

    setGdriveSaving(true);
    try {
      for (const key of activeKeys) {
        let downloadType = key;
        if (key === 'tasks') {
          const data = await apiFetch(`/api/session/${sessionCode}/report`);
          const tasks = data.question_stats || [];
          for (const t of tasks) {
            await apiFetch(`/api/session/${sessionCode}/reports/save-gdrive?type=task&task_id=${t.task_id}&format=${format}`, { method: 'POST' });
          }
          continue;
        }

        await apiFetch(`/api/session/${sessionCode}/reports/save-gdrive?type=${downloadType === 'tests' ? 'test' : downloadType}&format=${format}`, { method: 'POST' });
      }
      add("All selected reports saved to Google Drive successfully!", "success");
      onClose();
    } catch (e) {
      add(e.message || "Failed to save reports to Google Drive", "error");
    } finally {
      setGdriveSaving(false);
    }
  };

  return React.createElement('div', {
    style: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100, padding: 20 }
  },
    React.createElement('div', {
      className: 'card',
      style: { width: '100%', maxWidth: 460, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '16px', padding: 24 }
    },
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 } },
        React.createElement('h3', { style: { margin: 0, fontSize: '1.2rem', fontWeight: 800 } }, '📦 Bulk Reports Export'),
        React.createElement('button', { className: 'btn btn-ghost btn-sm', style: { padding: 4, minWidth: 32 }, onClick: onClose }, '✕')
      ),

      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 14 } },
        React.createElement('div', null,
          React.createElement('div', { style: { fontSize: '0.8rem', fontWeight: 700, color: 'var(--text2)', marginBottom: 8 } }, '1. Select Reports to Include:'),
          React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
            [
              { key: 'gradebook', label: '📊 Student Marks Register' },
              { key: 'tasks', label: '📝 Task Reports (Individual Question-wise)' },
              { key: 'tests', label: '🧪 Test Reports' },
              { key: 'coding', label: '💻 Coding Reports' }
            ].map(item =>
              React.createElement('label', { key: item.key, style: { display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.85rem', cursor: 'pointer' } },
                React.createElement('input', {
                  type: 'checkbox',
                  checked: selectedTypes[item.key],
                  onChange: () => toggleType(item.key)
                }),
                React.createElement('span', null, item.label)
              )
            )
          )
        ),

        React.createElement('div', null,
          React.createElement('div', { style: { fontSize: '0.8rem', fontWeight: 700, color: 'var(--text2)', marginBottom: 8 } }, '2. Choose Format:'),
          React.createElement('div', { style: { display: 'flex', gap: 12 } },
            ['pdf', 'excel', 'csv'].map(f =>
              React.createElement('label', { key: f, style: { display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.85rem', cursor: 'pointer' } },
                React.createElement('input', {
                  type: 'radio',
                  name: 'bulk-format',
                  checked: format === f,
                  onChange: () => setFormat(f)
                }),
                React.createElement('span', { style: { textTransform: 'uppercase' } }, f === 'excel' ? 'Excel (.xlsx)' : f)
              )
            )
          )
        )
      ),

      React.createElement('div', { style: { display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 } },
        React.createElement('button', { className: 'btn btn-ghost btn-sm', onClick: onClose, disabled: exporting || gdriveSaving }, 'Cancel'),
        React.createElement('button', {
          className: `btn btn-ghost btn-sm ${exporting ? 'loading' : ''}`,
          onClick: handleDownload,
          disabled: exporting || gdriveSaving
        }, '⬇️ Download All'),
        React.createElement('button', {
          className: `btn btn-primary btn-sm ${gdriveSaving ? 'loading' : ''}`,
          onClick: handleSaveToGDrive,
          disabled: exporting || gdriveSaving
        }, '☁️ Save to Drive')
      )
    )
  );
}

// ─────────────────────────────────────────────
//  MAIN REPORTS PAGE
// ─────────────────────────────────────────────
function ReportsPage({ sessionCode }) {
  const [currentSessionCode, setCurrentSessionCode] = React.useState(sessionCode);
  const [activeTab, setActiveTab] = React.useState('overview');
  const [qTypeFilter, setQTypeFilter] = React.useState('all');
  const [report, setReport] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [showQBankPDF, setShowQBankPDF] = React.useState(false);
  const [showBulkExport, setShowBulkExport] = React.useState(false);
  const [pastSessions, setPastSessions] = React.useState([]);
  const { add } = React.useContext(AppCtx);

  async function loadPastSessions() {
    try {
      const user = JSON.parse(localStorage.getItem('cm_user') || '{}');
      if (user.email) {
        const data = await apiFetch(`/api/teacher/sessions?email=${encodeURIComponent(user.email)}`);
        setPastSessions(data || []);
      }
    } catch (e) {
      console.error("Failed to load past sessions", e);
    }
  }

  async function loadReport(code, silent) {
    if (!silent) setLoading(true); else setRefreshing(true);
    try {
      const data = await apiFetch(`/api/session/${code}/report`);
      setReport(data);
    } catch (e) {
      add(e.message, 'error');
    }
    setLoading(false);
    setRefreshing(false);
  }

  React.useEffect(() => {
    loadReport(currentSessionCode);
  }, [currentSessionCode]);

  React.useEffect(() => {
    loadPastSessions();
  }, []);

  const tabs = [
    { id: 'overview', label: '📈 Analytics Overview' },
    { id: 'sessions', label: '📋 Session Reports' },
    { id: 'tasks', label: '📝 Task Reports' },
    { id: 'test', label: '🧪 Test Reports' },
    { id: 'coding', label: '💻 Coding Reports' },
    { id: 'gradebook', label: '📊 Student Marks Register' }
  ];

  const coding_summary = report?.coding_summary || { avg_score: 0, top_coder: null };

  const renderTasksContent = () => {
    if (qTypeFilter === 'mcq') return React.createElement(MCQReportView, { report });
    if (qTypeFilter === 'short') return React.createElement(OpenAnswerReportView, { report, qType: 'short' });
    if (qTypeFilter === 'long') return React.createElement(OpenAnswerReportView, { report, qType: 'long' });
    return React.createElement(TaskReportsTab, { report, sessionCode: currentSessionCode });
  };

  return React.createElement('div', { className: 'page' },
    React.createElement('style', null, `
      @keyframes rpt-pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.8; } }
      @keyframes rpt-fade-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      .rpt-content { animation: rpt-fade-in 0.3s ease; }
    `),

    // Header
    React.createElement('div', {
      style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24, flexWrap: 'wrap', gap: 12 }
    },
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' } },
        React.createElement('div', null,
          React.createElement('h1', { style: { fontSize: '1.4rem', fontWeight: 800, marginBottom: 2, background: 'linear-gradient(135deg, var(--accent), var(--accent2))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' } }, '📊 Reports Dashboard'),
          React.createElement('div', { style: { fontSize: '0.78rem', color: 'var(--text3)' } }, `Session ${currentSessionCode} · ${report ? `${report.students?.length || 0} students · ${report.total_tasks || 0} tasks` : 'Loading…'}`)
        ),
        pastSessions.length > 0 && React.createElement('select', {
          className: 'prof-settings-input',
          value: currentSessionCode,
          onChange: (e) => setCurrentSessionCode(e.target.value),
          style: { fontSize: '0.8rem', padding: '6px 10px', height: 'auto', background: 'var(--surface2)', color: 'var(--text)' }
        },
          pastSessions.map(ps => 
            React.createElement('option', { key: ps.code, value: ps.code }, `${ps.name || `Session ${ps.code}`} (${ps.date})`)
          )
        )
      ),
      React.createElement('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } },
        React.createElement('button', {
          className: 'btn btn-ghost btn-sm',
          onClick: () => loadReport(currentSessionCode, true),
          disabled: refreshing,
          style: { opacity: refreshing ? 0.6 : 1 }
        }, refreshing ? '⏳ Refreshing…' : '🔄 Refresh'),
        report?.question_stats?.length > 0 && React.createElement('button', {
          className: 'btn btn-ghost btn-sm',
          onClick: () => setShowQBankPDF(true)
        }, '📄 Question Bank'),
        React.createElement('button', {
          className: 'btn btn-ghost btn-sm',
          onClick: () => setShowBulkExport(true)
        }, '📦 Bulk Export'),
        React.createElement('button', {
          className: 'btn btn-primary btn-sm',
          onClick: async () => {
            try {
              const res = await fetch(`${API}/api/session/${currentSessionCode}/report/download`);
              const data = await res.json();
              const codingLine = `\n\n"Coding Performance"\n"Avg Score",${coding_summary.avg_score}%\n"Top Coder","${coding_summary.top_coder?.name || 'N/A'}"\n`;
              const blob = new Blob([data.csv + codingLine], { type: 'text/csv' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url; a.download = `report_${currentSessionCode}.csv`; a.click();
              URL.revokeObjectURL(url);
              add('Report downloaded!', 'success');
            } catch (e) { add('Download failed', 'error'); }
          }
        }, '⬇ Download CSV'),
        React.createElement('button', {
          className: 'btn btn-sm',
          style: {
            background: 'linear-gradient(135deg, #a855f7, #6366f1)',
            border: 'none',
            color: '#fff',
            fontWeight: '600',
            boxShadow: '0 0 12px rgba(168, 85, 247, 0.4)'
          },
          onClick: () => {
            window.open(`/session/${currentSessionCode}/premium-report`, '_blank');
          }
        }, '✨ View Premium Report')
      )
    ),

    // PDF Modal
    showQBankPDF && React.createElement(PDFOptionsModal, {
      tasks: (report?.question_stats || []).map(q => ({
        id: q.task_id, question: q.question, type: q.type || 'mcq',
        topic: q.topic, correct_answer: q.correct_answer, options: q.options
      })),
      title: `Session ${currentSessionCode} — Question Bank`,
      onClose: () => setShowQBankPDF(false)
    }),

    // Bulk Export Modal
    showBulkExport && React.createElement(BulkExportModal, {
      sessionCode: currentSessionCode,
      onClose: () => setShowBulkExport(false)
    }),

    // Loading skeleton
    loading
      ? React.createElement('div', { style: { padding: '60px 0' } },
          React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 14, marginBottom: 24 } },
            Array.from({ length: 8 }).map((_, i) =>
              React.createElement('div', { key: i, style: { height: 90, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, animation: 'rpt-pulse 1.4s ease-in-out infinite', animationDelay: `${i * 0.1}s` } })
            )
          ),
          React.createElement(RptSkeleton, { rows: 5, height: 200 })
        )
      : React.createElement('div', { className: 'rpt-content' },
          // Primary tab nav (Overview / Sessions / Tasks / Test / Coding / Gradebook)
          React.createElement(RptTabNav, { tabs, active: activeTab, onTab: setActiveTab }),

          // Question Type Filter — shown only on Tasks tab
          activeTab === 'tasks' && React.createElement(QuestionTypeFilterBar, { active: qTypeFilter, onChange: setQTypeFilter }),

          // Tab content
          activeTab === 'overview' && React.createElement(OverviewDashboard, { report, sessionCode: currentSessionCode }),
          activeTab === 'sessions' && React.createElement(SessionReportsTab, { report, sessionCode: currentSessionCode }),
          activeTab === 'tasks' && renderTasksContent(),
          activeTab === 'test' && React.createElement(TestReportsTab, { sessionCode: currentSessionCode }),
          activeTab === 'coding' && React.createElement(CodingReportsTab, { sessionCode: currentSessionCode }),
          activeTab === 'gradebook' && React.createElement(StudentMarksRegisterTab, { sessionCode: currentSessionCode, report })
        )
  );
}
"""

lines[target_start:target_end] = [new_components_and_page + '\n']

with open(html_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Replacement successful!")
