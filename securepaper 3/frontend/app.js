/* SecurePaper V3: role-aware, same-origin examination portal. */
(() => {
  'use strict';
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];
  const root = $('#root');
  const state = {
    user: null, csrf: '', roleChoice: null, page: 'dashboard', loading: false,
    catalog: null, studentData: null, teacherStats: null, students: [], exams: [], bank: [],
    assignment: null, attempt: null, questionIndex: 0, selectedExamId: '', resultExamId: '',
    resultsData: null, resultStudent: null, serverOffset: 0, unlocking: false, submitting: false,
    mobileNav: false, filter: '', pendingSaves: new Set(),
    practiceDraft: {subject:'',topic:'',question_count:10,duration_minutes:20,mode:'automatic'},
    practiceSelected: new Set(),
    examDraft: {name:'',subject:'',topic:'',question_count:5,duration_minutes:30,marks_per_question:1,
      negative_marks:0,set_count:2,scheduled_at:'',selection_mode:'automatic',assignmentsText:''},
    poolSelected: new Set(), manualSets: {}, activeManualSet:'A',
    showQuestionForm: false, editStudentId:'', pickerSearch:'', resultSearch:'', bankSearch:''
  };
  const glyphs = {
    grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    cap:'<path d="m2 9 10-5 10 5-10 5L2 9Z"/><path d="M6 11v6c4 4 8 4 12 0v-6"/><path d="M22 9v6"/>',
    calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',
    clipboard:'<rect x="6" y="4" width="12" height="17" rx="2"/><rect x="9" y="2" width="6" height="4" rx="1"/><path d="M9 11h6M9 15h6"/>',
    users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    book:'<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14Z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20"/>',
    chart:'<path d="M3 3v18h18"/><path d="M7 16v-5M12 16V7M17 16V4"/>',
    plus:'<path d="M12 5v14M5 12h14"/>',
    arrow:'<path d="M5 12h14M13 6l6 6-6 6"/>',
    left:'<path d="m15 18-6-6 6-6"/>',
    right:'<path d="m9 18 6-6-6-6"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
    lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 1 1 8 0v3"/>',
    logout:'<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    check:'<path d="m4 12 5 5L20 6"/>',
    upload:'<path d="M12 17V3M7 8l5-5 5 5M4 17v4h16v-4"/>',
    download:'<path d="M12 3v14m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    settings:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a2 2 0 0 0 .4 2.2l-2 2a2 2 0 0 0-2.2-.4l-1 1.7h-3l-1-1.7a2 2 0 0 0-2.2.4l-2-2A2 2 0 0 0 6.8 15l-1.8-1v-3l1.8-1a2 2 0 0 0-.4-2.2l2-2A2 2 0 0 0 10.6 6l1-1.7h3l1 1.7a2 2 0 0 0 2.2-.4l2 2a2 2 0 0 0-.4 2.2l1.7 1v3z"/>',
    menu:'<path d="M4 7h16M4 12h16M4 17h16"/>',
    close:'<path d="M5 5l14 14M19 5 5 19"/>',
    file:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/>',
    sparkle:'<path d="m12 2 2.8 7.2L22 12l-7.2 2.8L12 22l-2.8-7.2L2 12l7.2-2.8z"/>',
    filter:'<path d="M4 5h16M7 12h10M10 19h4"/>',
    mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 7 9-7"/>',
    edit:'<path d="M12 20h9M16 4l4 4L9 19H5v-4z"/>',
    eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>'
  };
  function icon(name, size = 19) { return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${glyphs[name] || glyphs.file}</svg>`; }
  function esc(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function attrs(value) { return esc(value); }
  function niceDate(value, time = true) { if (!value) return '—'; const d = new Date(value); return isNaN(d.getTime()) ? '—' : new Intl.DateTimeFormat('en-IN', {day:'2-digit',month:'short',year:'numeric', ...(time?{hour:'2-digit',minute:'2-digit'}:{})}).format(d); }
  function localTime(value) { const d = value || new Date(Date.now() + 3600000); const local = new Date(d.getTime() - d.getTimezoneOffset()*60000); return local.toISOString().slice(0,16); }
  const human = (x, digits = 2) => Number.isFinite(Number(x)) ? Number(x).toFixed(digits).replace(/\.00$/, '') : '—';
  const totalMarks = a => Number(a.total_questions || 0) * Number(a.marks_per_question || 1);
  const nowMs = () => Date.now() + state.serverOffset;
  function clock(delta) { const s = Math.max(0,Math.floor(delta/1000)); const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600), m=Math.floor((s%3600)/60), sec=s%60; return (d?`${d}d `:'')+`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`; }
  function statusBadge(status) { const cls = {'Upcoming':'upcoming','Available':'available','Completed':'completed','Submitted':'completed','In progress':'available','Not attempted':'muted','Not started':'muted'}[status]||'muted'; return `<span class="status ${cls}"><span class="status-dot"></span>${esc(status)}</span>`; }
  function setServerClock(value) { if (value) state.serverOffset = Date.parse(value) - Date.now(); }
  function toast(message, error = false) { const el=$('#toast'); el.textContent=message; el.className='toast show'+(error?' is-error':''); clearTimeout(toast.timer); toast.timer=setTimeout(()=>{el.className='toast';},3700); }
  function message(error) { if (!error) return 'Something went wrong.'; return error.message || 'Something went wrong.'; }
  async function api(path, opts = {}) {
    const headers = {'Accept':'application/json', ...(opts.body !== undefined ? {'Content-Type':'application/json'}:{}), ...(opts.method && opts.method !== 'GET' ? {'X-CSRF-Token':state.csrf}:{}), ...opts.headers};
    let response;
    try { response = await fetch(path,{credentials:'same-origin', ...opts, headers}); }
    catch (_) { throw new Error('Unable to connect. Please check your connection.'); }
    let data = null;
    try { data = await response.json(); } catch (_) { /* no JSON body */ }
    if (!response.ok) {
      let detail = data?.detail || `Request failed (${response.status}).`;
      if (Array.isArray(detail)) detail = detail.map(x => x.msg).join('; ');
      if (response.status===401 && state.user && !path.includes('/auth/login')) { state.user=null; state.csrf=''; state.roleChoice=null; state.page='dashboard'; render(); }
      throw new Error(detail);
    }
    return data;
  }
  const post = (path, data) => api(path,{method:'POST',body:JSON.stringify(data)});
  const patch = (path, data) => api(path,{method:'PATCH',body:JSON.stringify(data)});
  function initials(name) { return String(name || 'SP').split(/\s+/).slice(0,2).map(word=>word[0]||'').join('').toUpperCase(); }
  function brand(className = '') { return `<div class="brand ${className}"><span class="brand-icon">${icon('shield',23)}</span><span class="brand-text">Secure<span>Paper</span></span></div>`; }

  function landing() {
    const role = state.roleChoice;
    return `<main class="welcome-page">
      <section class="welcome-art">
        <div class="welcome-top">${brand('brand-light')}<span class="welcome-label">EXAMINATION PORTAL</span></div>
        <div class="welcome-content"><div class="welcome-eyebrow"><span class="eyebrow-line"></span> LEARNING, ORGANIZED</div>
          <h1>Every assessment.<br><span>One clear place.</span></h1>
          <p>A connected workspace for students and teachers—from first question to final result.</p>
          <div class="welcome-showcase" aria-hidden="true">
            <div class="showcase-decoration one"></div><div class="showcase-decoration two"></div>
            <div class="showcase-main"><div class="showcase-top"><span class="tiny-logo">${icon('clipboard',17)}</span> Examination overview <span class="showcase-dots">•••</span></div>
              <div class="showcase-value">Ready for what's next.</div><div class="showcase-track"><i></i><i></i><i></i><i></i><i></i></div>
              <div class="showcase-caption"><span>${icon('check',14)} Organized papers</span><span>${icon('clock',14)} Timed assessments</span></div></div>
            <div class="float-tile">${icon('chart',24)}<span>Results<br><strong>at a glance</strong></span></div>
          </div>
        </div>
        <div class="welcome-bottom">SECUREPAPER <span>EXAMINATION MANAGEMENT</span></div>
      </section>
      <section class="welcome-access">
        <div class="access-panel"><div class="portal-kicker">WELCOME TO SECUREPAPER</div>
          ${!role ? `<h2>Choose your portal</h2><p class="access-intro">Select how you would like to sign in.</p>
          <div class="role-choices">
            <button type="button" class="role-choice" data-action="choose-role" data-role="student"><span class="role-icon student-icon">${icon('cap',29)}</span><span class="role-info"><strong>Student Login</strong><small>Take examinations, practice and view your results</small></span>${icon('arrow',23)}</button>
            <button type="button" class="role-choice" data-action="choose-role" data-role="teacher"><span class="role-icon teacher-icon">${icon('users',27)}</span><span class="role-info"><strong>Teacher Login</strong><small>Manage students, examinations and performance</small></span>${icon('arrow',23)}</button>
          </div>` : `<button class="back-link" data-action="back-roles">${icon('left',17)} All portals</button>
          <div class="signin-mark ${role==='teacher'?'teacher-icon':'student-icon'}">${icon(role==='teacher'?'users':'cap',29)}</div>
          <h2>${role==='teacher'?'Teacher':'Student'} sign in</h2><p class="access-intro">Enter your credentials to access your workspace.</p>
          <form id="login-form" class="form-stack"><div class="field"><label for="login-id">${role==='teacher'?'Email address':'Roll number'}</label>
            <input class="field-input" id="login-id" name="identifier" type="${role==='teacher'?'email':'text'}" autocomplete="username" placeholder="${role==='teacher'?'name@school.edu':'Enter your roll number'}" required maxlength="120"></div>
            <div class="field"><label for="login-password">Password</label><input class="field-input" id="login-password" name="password" type="password" autocomplete="current-password" placeholder="Enter your password" required></div>
            <button type="submit" class="button primary full">Sign in to ${role==='teacher'?'Teacher':'Student'} Portal ${icon('arrow',17)}</button></form>`}
          <div class="access-bottom">${icon('shield',17)} Your personal examination workspace</div>
        </div>
      </section>
    </main>`;
  }

  function navItems() {
    return state.user.role==='teacher' ? [
      ['dashboard','Overview','grid'],['students','Students','users'],['new-exam','Create examination','plus'],
      ['exams','Examinations','clipboard'],['teacher-results','Results & analytics','chart'],['question-bank','Question bank','book'],['settings','Account settings','settings']
    ] : [
      ['dashboard','Overview','grid'],['practice','Create practice test','plus'],['available','Available tests','calendar'],
      ['student-results','My results','chart'],['settings','Account settings','settings']
    ];
  }
  function shell(content) {
    const user=state.user;
    const menu=navItems().map(([page,label,ico])=>`<button class="menu-link ${state.page===page?'active':''}" data-action="nav" data-page="${page}">${icon(ico,19)}<span>${esc(label)}</span>${state.page===page?'<i></i>':''}</button>`).join('');
    return `<div class="app-frame ${state.mobileNav?'nav-visible':''}">
      <aside class="sidebar"><div class="sidebar-head">${brand('brand-light')}<button class="mobile-close" data-action="close-menu" aria-label="Close menu">${icon('close')}</button></div>
        <div class="workspace-label">${user.role==='teacher'?'TEACHER WORKSPACE':'STUDENT WORKSPACE'}</div>
        <nav class="sidebar-nav" aria-label="Primary navigation">${menu}</nav>
        <div class="sidebar-bottom"><div class="account-row"><span class="avatar">${esc(initials(user.name))}</span><div><strong>${esc(user.name)}</strong><small>${user.role==='teacher'?'Teacher':`Roll ${esc(user.roll_number)}`}</small></div></div>
          <button class="logout-button" data-action="logout">${icon('logout',18)} Sign out</button></div>
      </aside><div class="sidebar-shade" data-action="close-menu"></div>
      <div class="app-area"><header class="app-topbar"><button class="hamburger" data-action="toggle-menu" aria-label="Open menu">${icon('menu',24)}</button>
        <div class="topbar-breadcrumb">WORKSPACE <span>/</span> <strong>${esc(pageName())}</strong></div>
        <div class="topbar-right"><span class="topbar-date">${niceDate(new Date(),false)}</span><span class="topbar-avatar">${esc(initials(user.name))}</span></div></header>
        <main class="page-container">${content}</main><footer class="app-footer">SecurePaper <span>Examination Management</span></footer></div></div>`;
  }
  function pageName() { return ({dashboard:'Overview',practice:'Create practice test',available:'Available tests','student-results':'My results',attempt:'Examination',result:'Result',lock:'Examination',students:'Students','new-exam':'Create examination',exams:'Examinations','exam-detail':'Examination details','teacher-results':'Results','question-bank':'Question bank',settings:'Settings'})[state.page]||'Overview'; }
  function pageHeader(kicker,title,subtitle,actions='') { return `<section class="page-heading"><div><span class="section-kicker">${esc(kicker)}</span><h1>${esc(title)}</h1>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div>${actions?`<div class="heading-actions">${actions}</div>`:''}</section>`; }
  function statCard(label,value,ico,tone='indigo',extra='') { return `<div class="metric-card"><span class="metric-icon ${tone}">${icon(ico,22)}</span><div><span class="metric-label">${esc(label)}</span><div class="metric-value">${esc(value)}</div>${extra?`<div class="metric-extra">${esc(extra)}</div>`:''}</div></div>`; }
  function empty(text,ico='clipboard',action='') { return `<div class="empty-state"><div class="empty-symbol">${icon(ico,30)}</div><strong>${esc(text)}</strong>${action}</div>`; }
  function cardTitle(name,sub='',actions='') { return `<div class="panel-header"><div><h3>${esc(name)}</h3>${sub?`<p>${esc(sub)}</p>`:''}</div>${actions}</div>`; }
  function button(label,action,cls='primary',iconName='arrow') {return `<button class="button ${cls}" data-action="${action}">${esc(label)} ${icon(iconName,16)}</button>`;}
  function subjectOptions(value, allowAll = false) { return `${allowAll?'<option value="">All subjects</option>':''}${(state.catalog?.subjects||[]).map(s=>`<option value="${attrs(s.name)}" ${s.name===value?'selected':''}>${esc(s.name)}</option>`).join('')}`; }
  function topicOptions(subject,topic) { const topics=state.catalog?.subjects.find(x=>x.name===subject)?.topics||[]; return `<option value="">All topics</option>${topics.map(t=>`<option value="${attrs(t.name)}" ${t.name===topic?'selected':''}>${esc(t.name)} (${t.count})</option>`).join('')}`; }
  function assignmentsTable(rows, compact=false) { return `<div class="table-scroll"><table class="data-table"><thead><tr><th>Examination</th><th>Subject</th><th>Paper</th><th>Schedule</th><th>Status</th><th></th></tr></thead><tbody>
    ${rows.map(a=>`<tr><td><strong>${esc(a.name)}</strong><div class="cell-sub">${a.question_count} questions · ${a.duration_minutes} min</div></td><td>${esc(a.subject)}</td><td><span class="set-pill">Set ${esc(a.paper_set)}</span></td><td>${niceDate(a.scheduled_at)}</td><td>${statusBadge(a.status)}</td><td><button class="text-button" data-action="open-assignment" data-id="${attrs(a.assignment_id)}">${a.status==='Upcoming'?'View':a.attempt_id?'Open':'Enter'} ${icon('right',14)}</button></td></tr>`).join('')||`<tr><td colspan="6">${empty('No examinations assigned yet.','calendar')}</td></tr>`}
    </tbody></table></div>`; }

  function studentDashboard() {
    const data=state.studentData||{assignments:[],attempts:[]};
    const upcoming=data.assignments.filter(a=>a.status==='Upcoming').length;
    const available=data.assignments.filter(a=>a.status==='Available').length;
    const completed=data.attempts.filter(a=>a.status==='submitted').length;
    const practiced=data.attempts.filter(a=>a.kind==='practice').length;
    return `${pageHeader('STUDENT PORTAL',`Good ${new Date().getHours()<12?'morning':new Date().getHours()<17?'afternoon':'evening'}, ${state.user.name.split(' ')[0]}.`,'Your learning and examinations, all in one place.',button('Create practice test','go-practice'))}
      <div class="welcome-strip"><div><span class="strip-eyebrow">YOUR EXAMINATION SPACE</span><h2>Focus on your next milestone.</h2><p>Check assigned papers, take practice tests, and track your progress.</p><button class="button light" data-action="nav" data-page="available">View available tests ${icon('arrow',16)}</button></div><div class="strip-art"><span>${icon('book',58)}</span><i></i></div></div>
      <div class="metrics-grid">${statCard('Available tests',available,'clipboard','mint')}${statCard('Upcoming tests',upcoming,'calendar','amber')}${statCard('Completed attempts',completed,'check','indigo')}${statCard('Practice tests',practiced,'book','rose')}</div>
      <div class="split-grid"><section class="panel">${cardTitle('Assigned examinations','Your upcoming and available papers',`<button class="quiet-link" data-action="nav" data-page="available">View all ${icon('arrow',15)}</button>`)}
        ${assignmentsTable(data.assignments.slice(0,5),true)}</section>
        <section class="panel">${cardTitle('Recent activity','Your latest attempts')}
        <div class="activity-list">${data.attempts.slice(0,5).map(a=>`<button class="activity-item" data-action="open-attempt" data-id="${attrs(a.id)}"><span class="activity-icon">${icon(a.kind==='practice'?'book':'clipboard',19)}</span><span><strong>${esc(a.title)}</strong><small>${niceDate(a.started_at)} · ${esc(a.kind==='practice'?'Practice':'Examination')}</small></span><span class="activity-score">${a.status==='submitted'?human(a.score):'Continue'} ${icon('right',15)}</span></button>`).join('')||empty('Your activity will appear here.','chart')}</div></section></div>`;
  }
  function teacherDashboard() {
    const stats=state.teacherStats||{students:0,exams:0,questions:0,assigned:0};
    return `${pageHeader('TEACHER PORTAL',`Welcome back, ${state.user.name.split(' ')[0]}.`,'Manage assessments, students and performance from one workspace.',button('New examination','go-new-exam'))}
      <div class="teacher-hero"><div><span class="strip-eyebrow">EXAMINATION CONTROL CENTER</span><h2>Teaching made more organized.</h2><p>Build papers, assign sets and review each student's progress.</p><button class="button light" data-action="nav" data-page="students">Manage students ${icon('arrow',16)}</button></div><div class="hero-orbit">${icon('cap',58)}<i></i></div></div>
      <div class="metrics-grid">${statCard('My students',stats.students,'users','indigo')}${statCard('Examinations',stats.exams,'clipboard','mint')}${statCard('Question bank',stats.questions,'book','amber')}${statCard('Paper assignments',stats.assigned,'file','rose')}</div>
      <section class="panel">${cardTitle('Recent examinations','Papers, schedules and assigned students',`<button class="quiet-link" data-action="nav" data-page="exams">All examinations ${icon('arrow',15)}</button>`)}${examTable(state.exams.slice(0,8))}</section>`;
  }
  function examTable(exams) { return `<div class="table-scroll"><table class="data-table"><thead><tr><th>Examination</th><th>Subject</th><th>Paper sets</th><th>Assigned</th><th>Schedule</th><th>Status</th><th></th></tr></thead><tbody>
    ${exams.map(e=>`<tr><td><strong>${esc(e.name)}</strong><div class="cell-sub">${e.question_count} questions · ${e.duration_minutes} min</div></td><td>${esc(e.subject)}</td><td>${e.set_count}</td><td>${e.assigned_count}</td><td>${niceDate(e.scheduled_at)}</td><td>${statusBadge(e.status)}</td><td><button class="text-button" data-action="open-teacher-exam" data-id="${attrs(e.id)}">Details ${icon('right',14)}</button></td></tr>`).join('')||`<tr><td colspan="7">${empty('No examinations created yet.','clipboard',button('Create examination','go-new-exam','primary','plus'))}</td></tr>`}
    </tbody></table></div>`; }

  function questionPicker(questions, selected, action, max=40) {
    return `<div class="question-picker"><div class="picker-heading"><strong>Question bank selection</strong><span>${selected.size} selected ${max?`/ ${max}`:''}</span></div>
       <div class="picker-search">${icon('search',17)}<input type="search" id="picker-search" placeholder="Search questions or topics" value="${attrs(state.pickerSearch)}" autocomplete="off"></div>
       <div class="picker-list">${questions.map((q,i)=>`<button type="button" class="picker-question ${selected.has(q.id)?'is-selected':''}" data-action="${action}" data-id="${attrs(q.id)}" data-question-search-item data-text="${attrs((q.text+' '+q.topic).toLowerCase())}">
         <span class="picker-check">${selected.has(q.id)?icon('check',14):''}</span><span class="picker-question-content"><strong>${esc(q.text)}</strong><small>${esc(q.topic)} · ${esc(q.difficulty)} · ${esc(q.question_type)}</small></span></button>`).join('')||empty('No matching questions.','book')}</div></div>`;
  }
  function practicePage() {
    const d=state.practiceDraft;
    const q=(state.bank||[]).filter(x=>x.subject===d.subject&&(!d.topic||x.topic===d.topic));
    return `${pageHeader('SELF-PRACTICE','Build your practice test','Choose what you want to work on, then begin immediately.')}
      <div class="form-layout"><section class="panel"><div class="panel-padded">${cardTitle('Test settings','Personalize your assessment')}
        <form id="practice-form" class="form-content"><div class="form-grid two"><div class="field"><label>Subject</label><select name="subject" class="field-input" required>${subjectOptions(d.subject)}</select></div><div class="field"><label>Topic</label><select name="topic" class="field-input">${topicOptions(d.subject,d.topic)}</select></div></div>
        <div class="form-grid two"><div class="field"><label>Number of questions</label><input name="question_count" class="field-input" type="number" min="1" max="40" value="${attrs(d.question_count)}" required></div><div class="field"><label>Duration (minutes)</label><input name="duration_minutes" class="field-input" type="number" min="1" max="180" value="${attrs(d.duration_minutes)}" required></div></div>
        <div class="field"><label>Question selection</label><div class="segmented"><button type="button" data-action="practice-mode" data-mode="automatic" class="${d.mode==='automatic'?'selected':''}">Select automatically</button><button type="button" data-action="practice-mode" data-mode="manual" class="${d.mode==='manual'?'selected':''}">Choose questions</button></div></div>
        ${d.mode==='manual'?questionPicker(q,state.practiceSelected,'toggle-practice',Number(d.question_count)):`<div class="selection-summary"><div class="summary-icon">${icon('sparkle',22)}</div><div><strong>${q.length} eligible questions</strong><span>Questions are selected from your chosen subject and topic.</span></div></div>`}
        <button type="submit" class="button primary full spacious">Create Test ${icon('arrow',18)}</button></form></div></section>
        <aside class="form-aside"><div class="aside-highlight"><span class="aside-symbol">${icon('cap',30)}</span><h3>Practice with purpose.</h3><p>Work at your own pace and review your performance after submission.</p></div><div class="panel aside-note"><strong>Test overview</strong><div class="overview-row"><span>Subject</span><b>${esc(d.subject||'—')}</b></div><div class="overview-row"><span>Topic</span><b>${esc(d.topic||'All topics')}</b></div><div class="overview-row"><span>Questions</span><b>${esc(d.question_count)}</b></div><div class="overview-row"><span>Duration</span><b>${esc(d.duration_minutes)} min</b></div></div></aside></div>`;
  }
  function availablePage() {
    const rows=state.studentData?.assignments||[];
    return `${pageHeader('EXAMINATIONS','Available tests','Your teacher-assigned papers and scheduled examinations.')}
      <div class="metrics-grid three">${statCard('Upcoming',rows.filter(x=>x.status==='Upcoming').length,'calendar','amber')}${statCard('Available now',rows.filter(x=>x.status==='Available').length,'clock','mint')}${statCard('Completed',rows.filter(x=>x.status==='Completed').length,'check','indigo')}</div>
      <section class="panel">${cardTitle('Assigned examinations','Only papers assigned to your roll number appear here.')}${assignmentsTable(rows)}</section>`;
  }
  function lockPage() {
    const a=state.assignment;
    if(!a) return empty('Examination unavailable.');
    return `${pageHeader('ASSIGNED EXAMINATION',a.name,`${a.subject} · Paper Set ${a.paper_set}`)}
      <div class="lock-card"><div class="lock-pattern" aria-hidden="true"></div><div class="lock-core"><div class="lock-glow"></div>${icon('lock',45)}</div>
      <span class="lock-eyebrow">PAPER LOCKED</span><h2>Your examination paper is secured and will unlock when the examination begins.</h2>
      <p>Scheduled for ${niceDate(a.scheduled_at)}</p><div class="lock-timer-label">TIME UNTIL EXAMINATION</div>
      <div class="lock-timer" data-countdown="${attrs(a.scheduled_at)}">${clock(Date.parse(a.scheduled_at)-nowMs())}</div>
      <div class="lock-facts"><div>${icon('file',17)} ${a.question_count} questions</div><div>${icon('clock',17)} ${a.duration_minutes} minutes</div><div>${icon('clipboard',17)} Set ${esc(a.paper_set)}</div></div>
      <button class="button outline-on-dark" data-action="nav" data-page="available">${icon('left',16)} Back to tests</button></div>`;
  }
  function examPage() {
    const a=state.attempt;
    if(!a) return empty('Examination unavailable.');
    if(a.status==='submitted') return resultPage();
    const q=a.questions||[], i=Math.max(0,Math.min(state.questionIndex,q.length-1)), question=q[i];
    const answered=q.filter(x=>x.selected_option).length;
    if (!question) return empty('No questions in this examination.');
    return `<div class="exam-header"><div><span class="section-kicker">${a.kind==='practice'?'SELF-PRACTICE':'ASSIGNED EXAMINATION'}</span><h1>${esc(a.title)}</h1><p>${esc(a.subject)}${a.topic?' · '+esc(a.topic):''} · ${q.length} questions</p></div>
      <div class="exam-timer">${icon('clock',23)}<div><span>TIME REMAINING</span><strong data-countdown="${attrs(a.deadline_at)}">${clock(Date.parse(a.deadline_at)-nowMs())}</strong></div></div></div>
      <div class="exam-progress"><div><strong>${answered} of ${q.length} answered</strong><span>${Math.round(100*answered/q.length)}% completed</span></div><div class="progress-track"><i style="width:${100*answered/q.length}%"></i></div></div>
      <div class="exam-layout"><section class="exam-question panel"><div class="exam-label-row"><span class="pill-soft">QUESTION ${i+1} / ${q.length}</span><span class="difficulty-label ${attrs(question.difficulty)}">${esc(question.difficulty)}</span></div>
        <div class="exam-question-text">${esc(question.text)}</div><div class="answer-choices">${question.options.map((op,oi)=>`<button class="answer-option ${question.selected_option===op.id?'chosen':''}" data-action="choose-option" data-q="${attrs(question.id)}" data-opt="${attrs(op.id)}"><span class="answer-letter">${'ABCD'[oi]}</span><span>${esc(op.text)}</span><span class="answer-radio">${question.selected_option===op.id?icon('check',13):''}</span></button>`).join('')}</div>
        <div class="exam-button-row"><button class="button secondary" data-action="exam-prev" ${i===0?'disabled':''}>${icon('left',16)} Previous</button><button class="button primary" data-action="exam-next" ${i===q.length-1?'disabled':''}>Next question ${icon('right',16)}</button></div>
      </section><aside class="exam-side panel"><h3>Question navigator</h3><p>Select a question to jump directly to it.</p>
      <div class="navigator-grid">${q.map((item,index)=>`<button class="nav-number ${item.selected_option?'done':''} ${index===i?'current':''}" data-action="exam-goto" data-index="${index}">${index+1}</button>`).join('')}</div>
      <div class="navigator-key"><span><i class="current"></i> Current</span><span><i class="done"></i> Answered</span><span><i></i> Not answered</span></div>
      <div class="exam-side-divider"></div><div class="completion-count"><span>Answered</span><strong>${answered} / ${q.length}</strong></div>
      <button class="button primary full" data-action="submit-exam">Submit examination ${icon('check',17)}</button></aside></div>`;
  }
  function resultPage() {
    const a=state.attempt;
    if(!a) return empty('No result selected.');
    const max=totalMarks(a),pct=max?100*(a.score||0)/max:0;
    return `${pageHeader('EXAMINATION RESULT','Your performance',`${a.title} · ${a.subject}`)}
      <section class="result-hero"><div class="result-emblem">${icon('check',31)}</div><span>EXAMINATION SUBMITTED</span><h2>Assessment complete.</h2><p>Your responses have been recorded successfully.</p>
      <div class="score-pill"><strong>${human(a.score)} <em>/ ${human(max)}</em></strong><span>MARKS OBTAINED</span></div></section>
      <div class="metrics-grid three">${statCard('Percentage',`${human(pct)}%`,'chart','indigo')}${statCard('Correct answers',a.correct_count,'check','mint')}${statCard('Questions',a.total_questions,'clipboard','amber')}</div>
      ${a.review?`<section class="panel result-review">${cardTitle('Answer review','Your responses and correct answers')}
        ${a.review.map((r,i)=>`<div class="review-entry"><div class="review-num">${String(i+1).padStart(2,'0')}</div><div><strong>${esc(r.text)}</strong><p>Your answer: <span>${esc(r.selected_text||'Not answered')}</span></p><p>Correct answer: <b>${esc(r.correct_text)}</b></p></div><span class="review-symbol ${r.is_correct?'yes':'no'}">${icon(r.is_correct?'check':'close',17)}</span></div>`).join('')}</section>`:''}
      <div class="button-row">${button('My results','go-my-results','secondary','chart')}${button('Back to overview','go-dashboard','primary','arrow')}</div>`;
  }
  function studentResults() {
    const attempts=state.studentData?.attempts||[];
    return `${pageHeader('PERFORMANCE','My results','Your practice and examination history.')}
      <section class="panel">${cardTitle('Attempt history',`${attempts.length} recorded attempts`)}
      <div class="table-scroll"><table class="data-table"><thead><tr><th>Assessment</th><th>Type</th><th>Date</th><th>Status</th><th>Marks</th><th></th></tr></thead><tbody>
      ${attempts.map(a=>`<tr><td><strong>${esc(a.title)}</strong><div class="cell-sub">${esc(a.subject)} · ${a.total_questions} questions</div></td><td>${a.kind==='practice'?'Practice':'Examination'}</td><td>${niceDate(a.started_at)}</td><td>${statusBadge(a.status==='submitted'?'Completed':'Available')}</td><td><strong>${a.status==='submitted'?`${human(a.score)} / ${human(totalMarks(a))}`:'—'}</strong></td><td><button class="text-button" data-action="open-attempt" data-id="${attrs(a.id)}">${a.status==='submitted'?'Result':'Continue'} ${icon('right',15)}</button></td></tr>`).join('')||`<tr><td colspan="6">${empty('You have no recorded attempts yet.','chart')}</td></tr>`}</tbody></table></div></section>`;
  }
  function studentsPage() {
    const editing=state.students.find(s=>s.id===state.editStudentId);
    const matches=state.students.filter(x=>(x.name+' '+x.roll_number).toLowerCase().includes(state.filter.toLowerCase()));
    return `${pageHeader('PEOPLE','Student management','Create accounts, manage credentials and keep student records up to date.')}
      <div class="two-panel-layout"><section class="panel">${cardTitle('Registered students',`${state.students.length} students in your workspace`)}
      <div class="table-toolbar"><div class="toolbar-search">${icon('search',17)}<input type="search" id="student-filter" placeholder="Search name or roll number" value="${attrs(state.filter)}"></div></div>
      <div class="table-scroll"><table class="data-table"><thead><tr><th>Student</th><th>Roll number</th><th>Status</th><th></th></tr></thead><tbody>
      ${matches.map(s=>`<tr><td><div class="user-cell"><span class="mini-avatar">${esc(initials(s.name))}</span><b>${esc(s.name)}</b></div></td><td><code class="roll-code">${esc(s.roll_number)}</code></td><td>${statusBadge(s.active?'Available':'Not attempted').replace('Available','Active').replace('Not attempted','Inactive')}</td><td><button class="text-button" data-action="edit-student" data-id="${attrs(s.id)}">Edit ${icon('edit',14)}</button></td></tr>`).join('')||`<tr><td colspan="4">${empty('No matching students.','users')}</td></tr>`}</tbody></table></div></section>
      <aside class="panel padded"><div class="side-card-heading"><span class="heading-icon">${icon(editing?'edit':'plus',21)}</span><div><h3>${editing?'Edit student':'Add new student'}</h3><p>${editing?'Update this student account.':'Create an account and login credentials.'}</p></div></div>
        <form id="student-form" class="form-content"><input type="hidden" name="student_id" value="${attrs(editing?.id||'')}">
          <div class="field"><label>Student name</label><input class="field-input" name="name" value="${attrs(editing?.name||'')}" placeholder="Full name" maxlength="100" required></div>
          <div class="field"><label>Roll number</label><input class="field-input" name="roll_number" value="${attrs(editing?.roll_number||'')}" placeholder="e.g. 101" maxlength="40" required></div>
          <div class="field"><label>${editing?'New password (leave blank to keep existing)':'Login password'}</label><input type="password" class="field-input" name="password" autocomplete="new-password" minlength="8" placeholder="${editing?'Optional':'At least 8 characters'}" ${editing?'':'required'}></div>
          <button type="submit" class="button primary full">${editing?'Save changes':'Create student account'} ${icon('check',17)}</button>
          ${editing?`<button type="button" class="button ${editing.active?'danger-outline':'secondary'} full" data-action="toggle-student-active" data-id="${attrs(editing.id)}" data-active="${editing.active?'false':'true'}">${editing.active?'Deactivate account':'Reactivate account'}</button><button type="button" class="button subtle full" data-action="cancel-edit-student">Cancel editing</button>`:''}
        </form></aside></div>`;
  }
  function currentSubjectQuestions() {
    const d=state.examDraft;
    return state.bank.filter(q=>q.active&&q.subject===d.subject&&(!d.topic||q.topic===d.topic));
  }
  function assignmentPreview(text, labels) {
    const lines=String(text||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean).filter(x=>!/^roll[_ ]?(number|no)?\b/i.test(x));
    const entries=lines.map((line,index)=>{const p=line.split(',').map(x=>x.trim());return {roll_number:p[0],set_label:(p[1]||labels[index%labels.length]||'A').toUpperCase()};});
    return `<div class="assignment-preview"><strong>${entries.length} roll numbers entered</strong><div class="preview-tags">${entries.slice(0,15).map(r=>`<span>${esc(r.roll_number)} <b>→ ${esc(r.set_label)}</b></span>`).join('')}${entries.length>15?`<span>+${entries.length-15} more</span>`:''}</div></div>`;
  }
  function examCreatePage() {
    const d=state.examDraft;
    if(!d.scheduled_at) d.scheduled_at=localTime();
    const labels=listLabels(d.set_count), eligible=currentSubjectQuestions();
    const selected = d.selection_mode==='manual' ? (state.manualSets[state.activeManualSet]||new Set()) : state.poolSelected;
    const manual= d.selection_mode==='manual';
    return `${pageHeader('ASSESSMENT BUILDER','Create examination','Configure your paper, select students and schedule the assessment.')}
      <form id="exam-create-form" class="exam-create-grid">
        <section class="panel padded exam-details">${cardTitle('01 / Examination details','Basic information and assessment settings')}
          <div class="field"><label>Examination name</label><input class="field-input" name="name" maxlength="120" value="${attrs(d.name)}" placeholder="e.g. Midterm Assessment" required></div>
          <div class="form-grid two"><div class="field"><label>Subject</label><select class="field-input" name="subject" required>${subjectOptions(d.subject)}</select></div><div class="field"><label>Topic</label><select class="field-input" name="topic">${topicOptions(d.subject,d.topic)}</select></div></div>
          <div class="form-grid two"><div class="field"><label>Questions per paper</label><input class="field-input" name="question_count" type="number" min="1" max="40" value="${attrs(d.question_count)}" required></div><div class="field"><label>Duration (minutes)</label><input class="field-input" name="duration_minutes" type="number" min="1" max="180" value="${attrs(d.duration_minutes)}" required></div></div>
          <div class="form-grid two"><div class="field"><label>Marks per question</label><input class="field-input" name="marks_per_question" type="number" step="0.25" min="0.25" max="100" value="${attrs(d.marks_per_question)}" required></div><div class="field"><label>Negative marking</label><input class="field-input" name="negative_marks" type="number" step="0.25" min="0" max="100" value="${attrs(d.negative_marks)}" required></div></div>
          <div class="field"><label>Scheduled start (your local time)</label><input class="field-input" name="scheduled_at" type="datetime-local" value="${attrs(d.scheduled_at)}" required></div>
        </section>
        <section class="panel padded exam-paper-settings">${cardTitle('02 / Question paper sets','Build distinct paper combinations')}
          <div class="form-grid two"><div class="field"><label>Number of paper sets</label><select name="set_count" class="field-input">${[1,2,3,4,5,6].map(i=>`<option value="${i}" ${Number(d.set_count)===i?'selected':''}>${i} ${i===1?'set':'sets'}${i>1?' (A–'+String.fromCharCode(64+i)+')':''}</option>`).join('')}</select></div><div class="field"><label>Questions available</label><div class="readonly-stat">${eligible.length} in bank</div></div></div>
          <div class="field"><label>Question selection</label><div class="segmented"><button type="button" class="${!manual?'selected':''}" data-action="exam-mode" data-mode="automatic">Automatic sets</button><button type="button" class="${manual?'selected':''}" data-action="exam-mode" data-mode="manual">Choose per set</button></div></div>
          ${manual?`<div class="paper-set-tabs">${labels.map(label=>`<button type="button" class="paper-tab ${state.activeManualSet===label?'active':''}" data-action="manual-tab" data-label="${label}">Paper ${label}<span>${state.manualSets[label]?.size||0}/${d.question_count}</span></button>`).join('')}</div>`:''}
          ${questionPicker(eligible,selected,manual?'toggle-manual-question':'toggle-pool-question',manual?Number(d.question_count):0)}
          <div class="picker-footnote">${manual?'Choose exactly '+d.question_count+' questions for each paper set.':'Optional: select a pool of questions, or leave everything unselected to use the full eligible bank.'}</div>
        </section>
        <section class="panel padded exam-assignments">${cardTitle('03 / Assign students','Enter roll numbers or upload a CSV list')}
          <div class="form-grid assignment-grid"><div class="field"><label>Roll numbers (one per line)</label><textarea class="field-input assignment-textarea" name="assignmentsText" placeholder="101,A&#10;102,B&#10;103,C&#10;104,A" required>${esc(d.assignmentsText)}</textarea><small class="field-hint">Use <b>101,A</b> to choose a paper set, or just <b>101</b> for automatic rotation.</small></div>
            <div><label class="upload-box" for="assignment-file">${icon('upload',28)}<strong>Import roll numbers</strong><span>Choose a CSV or text file</span><span class="button secondary compact">Browse file</span></label><input type="file" id="assignment-file" accept=".csv,.txt,text/csv,text/plain" hidden>
              <div class="student-count-note">${icon('users',18)} ${state.students.filter(x=>x.active).length} active students</div></div></div>
          <div id="assignment-preview-wrap">${assignmentPreview(d.assignmentsText,labels)}</div>
          <div class="create-exam-actions"><span>${icon('calendar',19)} Students can enter the paper at the scheduled start.</span><button class="button primary spacious" type="submit">Create Test ${icon('arrow',18)}</button></div>
        </section>
      </form>`;
  }
  function listLabels(count) {return [...'ABCDEF'].slice(0,Number(count)||1);}
  function teacherExamsPage() {return `${pageHeader('EXAMINATION LIBRARY','Your examinations','Manage papers, assignments and scheduled assessments.',button('Create examination','go-new-exam','primary','plus'))}<section class="panel">${cardTitle('Examination records',`${state.exams.length} examinations`)}${examTable(state.exams)}</section>`;}
  function teacherExamDetailPage() {
    const detail=state.examDetail;
    if (!detail) return empty('Examination not found.');
    const ex=detail.exam, started=nowMs()>=Date.parse(ex.scheduled_at), labels=detail.sets.map(s=>s.label);
    return `${pageHeader('EXAMINATION DETAILS',ex.name,`${ex.subject}${ex.topic?' · '+ex.topic:''}`,
      `<button class="button secondary" data-action="nav" data-page="exams">${icon('left',16)} All examinations</button><button class="button primary" data-action="view-exam-results" data-id="${attrs(ex.id)}">Results ${icon('arrow',16)}</button>`)}
      <div class="metrics-grid">${statCard('Paper sets',detail.sets.length,'file','indigo')}${statCard('Questions per set',ex.question_count,'book','mint')}${statCard('Assigned students',detail.assignments.length,'users','amber')}${statCard('Duration',`${ex.duration_minutes} min`,'clock','rose')}</div>
      <div class="two-panel-layout"><section class="panel">${cardTitle('Roll number assignments',`${niceDate(ex.scheduled_at)} · ${human(ex.marks_per_question)} marks each`)}
        <div class="table-scroll"><table class="data-table"><thead><tr><th>Roll number</th><th>Student</th><th>Assigned paper</th></tr></thead><tbody>${detail.assignments.map(a=>`<tr><td><code class="roll-code">${esc(a.roll_number)}</code></td><td>${esc(a.name)}</td><td><span class="set-pill">Paper ${esc(a.paper_set)}</span></td></tr>`).join('')}</tbody></table></div>
      </section><aside class="panel padded"><div class="side-card-heading"><span class="heading-icon">${icon('users',21)}</span><div><h3>Manage assignments</h3><p>${started?'Assignments are closed for this examination.':'Add or reassign student paper sets.'}</p></div></div>
        ${!started?`<form id="assign-extra-form" class="form-content"><div class="field"><label>Roll numbers and paper sets</label><textarea name="assignments" class="field-input assignment-textarea" placeholder="101,A&#10;102,B&#10;103,C" required></textarea><small class="field-hint">Available sets: ${labels.join(', ')}.</small></div><button type="submit" class="button primary full">Save assignments ${icon('check',17)}</button></form>`:''}
        <div class="paper-legend"><strong>Paper sets</strong>${detail.sets.map(s=>`<div><span class="set-pill">Paper ${esc(s.label)}</span><span>${s.question_ids.length} questions</span></div>`).join('')}</div></aside></div>`;
  }
  function teacherResultsPage() {
    const id=state.resultExamId||state.exams[0]?.id||'';
    const report=state.resultsData;
    if(!state.exams.length) return `${pageHeader('ANALYTICS','Results & analytics','Examination-wise student performance.')}${empty('Create an examination to see results.','chart',button('Create examination','go-new-exam','primary','plus'))}`;
    const rows=(report?.rows||[]).filter(r=>[r.name,r.roll_number,r.paper_set,r.submission_status].join(' ').toLowerCase().includes(state.resultSearch.toLowerCase()));
    return `${pageHeader('PERFORMANCE','Results & analytics','Exam-wise progress and individual student scores.')}
      <div class="results-toolbar"><div class="field"><label>Choose examination</label><select class="field-input" id="result-exam-select">${state.exams.map(ex=>`<option value="${attrs(ex.id)}" ${ex.id===id?'selected':''}>${esc(ex.name)} · ${esc(ex.subject)}</option>`).join('')}</select></div>
      <div class="results-buttons"><button class="button secondary" data-action="export-results" data-format="csv" ${!report?'disabled':''}>${icon('download',16)} Export CSV</button><button class="button primary" data-action="export-results" data-format="xlsx" ${!report?'disabled':''}>${icon('download',16)} Export Excel</button></div></div>
      ${report?`<div class="metrics-grid">${statCard('Total assigned',report.summary.total_assigned,'users','indigo')}${statCard('Attempted',report.summary.attempted,'check','mint')}${statCard('Not attempted',report.summary.not_attempted,'clock','amber')}${statCard('Submitted',report.summary.submitted,'clipboard','rose')}</div>
      <section class="panel">${cardTitle('Student performance',`${esc(report.exam.name)} · ${report.rows.length} assigned`)}
      <div class="table-toolbar"><div class="toolbar-search">${icon('search',17)}<input type="search" id="result-filter" value="${attrs(state.resultSearch)}" placeholder="Search roll, name, set or status"></div></div>
      <div class="table-scroll"><table class="data-table"><thead><tr><th>Student</th><th>Roll number</th><th>Paper</th><th>Marks</th><th>Percentage</th><th>Status</th><th></th></tr></thead><tbody>
      ${rows.map(r=>`<tr><td><strong>${esc(r.name)}</strong></td><td><code class="roll-code">${esc(r.roll_number)}</code></td><td><span class="set-pill">${esc(r.paper_set)}</span></td>
        <td><strong>${r.score===null?'—':human(r.score)} / ${human(r.total_marks)}</strong></td><td>${r.percentage===null?'—':`${human(r.percentage)}%`}</td><td>${statusBadge(r.submission_status)}</td>
        <td><button class="text-button" data-action="student-exam-detail" data-id="${attrs(r.student_id)}">Details ${icon('right',14)}</button></td></tr>`).join('')||`<tr><td colspan="7">${empty('No matching students.','chart')}</td></tr>`}</tbody></table></div></section>
      ${state.resultStudent?teacherResultDetail():''}`:`${empty('Select an examination to view its results.','chart')}`}`;
  }
  function teacherResultDetail() {
    const r=state.resultStudent;
    return `<div class="detail-overlay" data-action="close-result"><section class="detail-drawer" role="dialog" aria-modal="true" aria-label="Student examination result" data-stop="true">
      <div class="drawer-heading"><div><span class="section-kicker">INDIVIDUAL RESULT</span><h2>${esc(r.name)}</h2><p>Roll ${esc(r.roll_number)} · Paper ${esc(r.paper_set)}</p></div><button class="icon-button" data-action="close-result" aria-label="Close">${icon('close',21)}</button></div>
      <div class="drawer-summary"><div><small>Marks obtained</small><strong>${r.score===null?'—':human(r.score)}</strong></div><div><small>Correct answers</small><strong>${r.correct_count??'—'}</strong></div><div><small>Status</small><strong>${r.status||'Not attempted'}</strong></div></div>
      <div class="drawer-review">${r.review?.length? r.review.map((x,i)=>`<article><span>${i+1}. ${esc(x.text)}</span><p>Selected: ${esc(x.selected_text||'Not answered')}</p><p class="right-answer">Correct: ${esc(x.correct_text)}</p></article>`).join('') : empty('No attempted questions for this student.','file')}</div></section></div>`;
  }
  function questionBankPage() {
    const q=(state.bank||[]).filter(x=>[x.text,x.topic,x.subject,x.difficulty].join(' ').toLowerCase().includes(state.bankSearch.toLowerCase()));
    return `${pageHeader('CONTENT LIBRARY','Question bank','Manage tagged questions and answer options.',button('Add question','toggle-question-form','primary','plus'))}
      ${state.showQuestionForm?`<section class="panel padded add-question-panel">${cardTitle('Add a question','Store the verified correct answer and multiple distractors')}<form id="question-form" class="form-content">
        <div class="form-grid four"><div class="field"><label>Subject</label><input class="field-input" name="subject" list="subjects-datalist" placeholder="Subject" required><datalist id="subjects-datalist">${(state.catalog?.subjects||[]).map(s=>`<option value="${attrs(s.name)}"></option>`).join('')}</datalist></div>
          <div class="field"><label>Topic</label><input class="field-input" name="topic" placeholder="Topic" required></div>
          <div class="field"><label>Difficulty</label><select class="field-input" name="difficulty"><option>easy</option><option selected>medium</option><option>hard</option></select></div>
          <div class="field"><label>Question type</label><select class="field-input" name="question_type"><option>conceptual</option><option>numerical</option><option>application</option><option>reasoning</option></select></div></div>
        <div class="field"><label>Question</label><textarea class="field-input" name="text" placeholder="Enter the question" minlength="6" required></textarea></div>
        <div class="form-grid two"><div class="field"><label>Correct option</label><input class="field-input" name="correct_option" required placeholder="Correct answer"></div><div class="field"><label>Wrong options (one per line, minimum three)</label><textarea class="field-input" name="wrong_options" rows="4" required placeholder="Wrong option 1&#10;Wrong option 2&#10;Wrong option 3"></textarea></div></div>
        <div class="button-row"><button class="button primary" type="submit">Save question ${icon('check',16)}</button><button type="button" class="button secondary" data-action="toggle-question-form">Cancel</button></div></form></section>`:''}
      <div class="metrics-grid three">${statCard('All questions',state.bank.length,'book','indigo')}${statCard('Active questions',state.bank.filter(x=>x.active).length,'check','mint')}${statCard('Subjects',new Set(state.bank.map(x=>x.subject)).size,'file','amber')}</div>
      <section class="panel">${cardTitle('Stored questions','Expand a question to inspect its marked options',`<label class="button secondary compact upload-action">${icon('upload',16)} Import JSON<input type="file" id="question-import" accept=".json,application/json" hidden></label>`)}
        <div class="table-toolbar"><div class="toolbar-search">${icon('search',17)}<input type="search" id="bank-filter" placeholder="Search questions, subjects or topics" value="${attrs(state.bankSearch)}"></div></div>
        <div class="table-scroll"><table class="data-table question-table"><thead><tr><th>Question</th><th>Subject / Topic</th><th>Difficulty</th><th>Status</th><th>Actions</th></tr></thead><tbody>
          ${q.map(x=>`<tr><td class="question-cell"><details><summary>${esc(x.text)}</summary><div class="option-detail">${x.options.map(o=>`<div class="${o.is_correct?'is-correct':''}">${icon(o.is_correct?'check':'close',14)} ${esc(o.text)} <small>${o.is_correct?'Correct':'Incorrect'}</small></div>`).join('')}</div></details></td><td><strong>${esc(x.subject)}</strong><div class="cell-sub">${esc(x.topic)}</div></td><td><span class="difficulty-label ${attrs(x.difficulty)}">${esc(x.difficulty)}</span></td><td>${statusBadge(x.active?'Available':'Not attempted').replace('Available','Active').replace('Not attempted','Archived')}</td>
             <td><button class="text-button" data-action="toggle-bank-question" data-id="${attrs(x.id)}" data-active="${x.active?'false':'true'}">${x.active?'Archive':'Restore'}</button></td></tr>`).join('')||`<tr><td colspan="5">${empty('No questions match your search.','book')}</td></tr>`}</tbody></table></div></section>`;
  }
  function settingsPage() {return `${pageHeader('ACCOUNT','Account settings','Manage your login password.')}
    <section class="panel padded settings-card">${cardTitle('Change password','Update your account credentials')}
      <form id="password-form" class="form-content"><div class="field"><label>Current password</label><input class="field-input" type="password" name="old_password" autocomplete="current-password" required></div>
      <div class="field"><label>New password</label><input class="field-input" type="password" name="new_password" minlength="8" maxlength="128" autocomplete="new-password" required></div>
      <button type="submit" class="button primary">Save new password ${icon('check',17)}</button></form></section>`;}

  function render() {
    if(!state.user){root.innerHTML=landing();return;}
    let content='';
    switch(state.page){
      case 'dashboard':content=state.user.role==='teacher'?teacherDashboard():studentDashboard();break;
      case 'practice':content=practicePage();break;
      case 'available':content=availablePage();break;
      case 'lock':content=lockPage();break;
      case 'attempt':content=examPage();break;
      case 'result':content=resultPage();break;
      case 'student-results':content=studentResults();break;
      case 'students':content=studentsPage();break;
      case 'new-exam':content=examCreatePage();break;
      case 'exams':content=teacherExamsPage();break;
      case 'exam-detail':content=teacherExamDetailPage();break;
      case 'teacher-results':content=teacherResultsPage();break;
      case 'question-bank':content=questionBankPage();break;
      case 'settings':content=settingsPage();break;
      default:content=empty('Page not found.');
    }
    root.innerHTML=shell(content);
    if(state.pickerSearch)filterPicker(state.pickerSearch);
    refreshClocks();
  }
  function filterPicker(value){ $$('.picker-question').forEach(el=>{el.style.display=el.dataset.text.includes(String(value||'').toLowerCase())?'':'none';}); }
  function draftFromForm(form,destination){if(!form)return;new FormData(form).forEach((v,k)=>{if(!(v instanceof File)) destination[k]=v;});}
  async function loadCatalog(){if(!state.catalog){state.catalog=await api('/api/v3/catalog');setServerClock(state.catalog.server_now);}}
  async function refreshPage() {
    await loadCatalog();
    if(state.user.role==='student'){
      if(['dashboard','available','student-results'].includes(state.page)){state.studentData=await api('/api/v3/student/dashboard');setServerClock(state.studentData.server_now);}
      if(state.page==='practice'){state.bank=await api('/api/v3/questions');if(!state.practiceDraft.subject)state.practiceDraft.subject=state.catalog.subjects[0]?.name||'';}
      if(state.page==='lock'){const response=await api('/api/v3/student/assignments/'+encodeURIComponent(state.selectedAssignmentId));state.assignment=response.assignment;setServerClock(response.server_now);}
      if(['attempt','result'].includes(state.page)&&state.attempt){state.attempt=await api('/api/v3/student/attempts/'+encodeURIComponent(state.attempt.id));setServerClock(state.attempt.server_now);if(state.attempt.status==='submitted')state.page='result';}
    }else{
      if(state.page==='dashboard'){[state.teacherStats,state.exams]=await Promise.all([api('/api/v3/teacher/dashboard'),api('/api/v3/teacher/exams')]);}
      if(state.page==='students')state.students=await api('/api/v3/teacher/students');
      if(state.page==='new-exam'){[state.students,state.bank]=await Promise.all([api('/api/v3/teacher/students'),api('/api/v3/teacher/questions')]);if(!state.examDraft.subject)state.examDraft.subject=state.catalog.subjects[0]?.name||'';}
      if(state.page==='exams')state.exams=await api('/api/v3/teacher/exams');
      if(state.page==='exam-detail')state.examDetail=await api('/api/v3/teacher/exams/'+encodeURIComponent(state.selectedExamId));
      if(state.page==='teacher-results'){state.exams=await api('/api/v3/teacher/exams');if(!state.resultExamId)state.resultExamId=state.exams[0]?.id||'';if(state.resultExamId)state.resultsData=await api(`/api/v3/teacher/exams/${encodeURIComponent(state.resultExamId)}/results`);}
      if(state.page==='question-bank')state.bank=await api('/api/v3/teacher/questions');
    }
  }
  async function navigate(page) {
    if(!state.user)return;
    const allowed=navItems().map(x=>x[0]);
    if(![...allowed,'attempt','result','lock','exam-detail'].includes(page))return;
    if(['students','new-exam','exams','exam-detail','teacher-results','question-bank'].includes(page) && state.user.role!=='teacher')return;
    if(['practice','available','student-results','lock','attempt','result'].includes(page) && state.user.role!=='student')return;
    state.page=page;state.mobileNav=false;state.pickerSearch='';state.filter='';
    try {await refreshPage();render();window.scrollTo({top:0,behavior:'instant'});} catch(e){toast(message(e),true);render();}
  }
  async function openAssignment(id) {
    state.selectedAssignmentId=id;
    try{
      const result=await api('/api/v3/student/assignments/'+encodeURIComponent(id));
      state.assignment=result.assignment;setServerClock(result.server_now);
      if(result.assignment.attempt_id){await openAttempt(result.assignment.attempt_id);return;}
      if(result.assignment.status==='Completed'){toast('This examination is no longer available.',true);return;}
      if(result.assignment.status==='Upcoming'){state.page='lock';render();window.scrollTo(0,0);return;}
      await beginAssigned();
    }catch(e){toast(message(e),true);}
  }
  async function beginAssigned(){
    if(state.unlocking||!state.selectedAssignmentId)return;
    state.unlocking=true;
    try{const data=await post(`/api/v3/student/assignments/${encodeURIComponent(state.selectedAssignmentId)}/start`,{});await openAttempt(data.attempt_id);}catch(e){toast(message(e),true);}finally{state.unlocking=false;}
  }
  async function openAttempt(id){
    try{state.attempt=await api('/api/v3/student/attempts/'+encodeURIComponent(id));setServerClock(state.attempt.server_now);state.questionIndex=0;state.page=state.attempt.status==='submitted'?'result':'attempt';state.mobileNav=false;render();window.scrollTo(0,0);}catch(e){toast(message(e),true);}
  }
  async function submitCurrent(){
    if(!state.attempt||state.submitting)return;
    state.submitting=true;
    try{
      if(state.pendingSaves.size)await Promise.allSettled([...state.pendingSaves]);
      state.attempt=await post(`/api/v3/student/attempts/${encodeURIComponent(state.attempt.id)}/submit`,{});state.page='result';render();window.scrollTo(0,0);}catch(e){toast(message(e),true);}finally{state.submitting=false;}
  }
  function refreshClocks(){
    $$('[data-countdown]').forEach(el=>{const delta=Date.parse(el.dataset.countdown)-nowMs();el.textContent=clock(delta);if(delta<=0 && state.page==='lock' && !state.unlocking)beginAssigned();if(delta<=0 && state.page==='attempt' && !state.submitting)submitCurrent();});
  }
  setInterval(refreshClocks,1000);
  function parseRolls(text){
    const rows=String(text||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean).filter(x=>!/^roll[_ ]?(number|no)?\b/i.test(x));
    return rows.map(x=>{const parts=x.split(',').map(s=>s.trim());return {roll_number:parts[0],set_label:parts[1]||null};});
  }
  async function downloadReport(format){
    if(!state.resultExamId)return;
    try{const url=`/api/v3/teacher/exams/${encodeURIComponent(state.resultExamId)}/export?format=${format}`;
      const res=await fetch(url,{credentials:'same-origin'});
      if(!res.ok){const data=await res.json().catch(()=>({}));throw new Error(data.detail||'Could not export the report.');}
      const blob=await res.blob(), obj=URL.createObjectURL(blob),a=document.createElement('a');a.href=obj;a.download=`securepaper-results.${format}`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(obj),1000);
    }catch(e){toast(message(e),true);}
  }
  async function runAction(el){
    const action=el.dataset.action;
    switch(action){
      case 'choose-role':state.roleChoice=el.dataset.role;render();break;
      case 'back-roles':state.roleChoice=null;render();break;
      case 'toggle-menu':state.mobileNav=!state.mobileNav;render();break;
      case 'close-menu':state.mobileNav=false;render();break;
      case 'logout':try{await post('/api/v3/auth/logout',{});}catch(_){}state.user=null;state.csrf='';state.catalog=null;state.roleChoice=null;state.page='dashboard';render();break;
      case 'nav':await navigate(el.dataset.page);break;
      case 'go-practice':await navigate('practice');break;
      case 'go-new-exam':await navigate('new-exam');break;
      case 'go-my-results':await navigate('student-results');break;
      case 'go-dashboard':await navigate('dashboard');break;
      case 'practice-mode':state.practiceDraft.mode=el.dataset.mode;state.pickerSearch='';render();break;
      case 'exam-mode':draftFromForm($('#exam-create-form'),state.examDraft);state.examDraft.selection_mode=el.dataset.mode;state.pickerSearch='';render();break;
      case 'manual-tab':draftFromForm($('#exam-create-form'),state.examDraft);state.activeManualSet=el.dataset.label;state.pickerSearch='';render();break;
      case 'toggle-practice':{const id=el.dataset.id,d=state.practiceDraft;draftFromForm($('#practice-form'),d);if(state.practiceSelected.has(id))state.practiceSelected.delete(id);else if(state.practiceSelected.size<Number(d.question_count))state.practiceSelected.add(id);else{toast(`Select no more than ${d.question_count} questions.`,true);return;}render();break;}
      case 'toggle-manual-question':case 'toggle-pool-question':{
        draftFromForm($('#exam-create-form'),state.examDraft);const chosen=action==='toggle-manual-question'?(state.manualSets[state.activeManualSet] ||= new Set()):state.poolSelected,id=el.dataset.id;
        if(chosen.has(id))chosen.delete(id);else if(action==='toggle-manual-question'&&chosen.size>=Number(state.examDraft.question_count)){toast(`This set already has ${state.examDraft.question_count} questions.`,true);return;}else chosen.add(id);
        render();break;}
      case 'open-assignment':await openAssignment(el.dataset.id);break;
      case 'open-attempt':await openAttempt(el.dataset.id);break;
      case 'exam-goto':state.questionIndex=Number(el.dataset.index);render();break;
      case 'exam-prev':state.questionIndex=Math.max(0,state.questionIndex-1);render();break;
      case 'exam-next':state.questionIndex=Math.min((state.attempt?.questions?.length||1)-1,state.questionIndex+1);render();break;
      case 'choose-option':{
        const a=state.attempt,q=a?.questions?.find(q=>q.id===el.dataset.q);if(!q)return;
        q.selected_option=el.dataset.opt;render();
        const save=post(`/api/v3/student/attempts/${encodeURIComponent(a.id)}/answer`,{question_id:q.id,option_id:q.selected_option});
        state.pendingSaves.add(save);
        try{await save;}
        catch(e){toast(message(e),true);await openAttempt(a.id);}
        finally{state.pendingSaves.delete(save);}break;}
      case 'submit-exam':if(confirm('Submit your examination now?'))await submitCurrent();break;
      case 'edit-student':state.editStudentId=el.dataset.id;render();break;
      case 'cancel-edit-student':state.editStudentId='';render();break;
      case 'toggle-student-active':try{await patch(`/api/v3/teacher/students/${el.dataset.id}`,{active:el.dataset.active==='true'});state.students=await api('/api/v3/teacher/students');state.editStudentId='';render();toast('Student account updated.');}catch(e){toast(message(e),true);}break;
      case 'open-teacher-exam':state.selectedExamId=el.dataset.id;await navigate('exam-detail');break;
      case 'view-exam-results':state.resultExamId=el.dataset.id;state.resultStudent=null;await navigate('teacher-results');break;
      case 'export-results':await downloadReport(el.dataset.format);break;
      case 'student-exam-detail':try{state.resultStudent=await api(`/api/v3/teacher/exams/${encodeURIComponent(state.resultExamId)}/results/${encodeURIComponent(el.dataset.id)}`);render();}catch(e){toast(message(e),true);}break;
      case 'close-result':state.resultStudent=null;render();break;
      case 'toggle-question-form':state.showQuestionForm=!state.showQuestionForm;render();break;
      case 'toggle-bank-question':try{await api(`/api/v3/teacher/questions/${encodeURIComponent(el.dataset.id)}?active=${el.dataset.active}`,{method:'PATCH'});state.bank=await api('/api/v3/teacher/questions');render();toast('Question updated.');}catch(e){toast(message(e),true);}break;
    }
  }

  document.addEventListener('click',e=>{
    const el=e.target.closest('[data-action]');if(!el)return;
    if(el.dataset.action==='close-result' && el.classList.contains('detail-overlay') && e.target.closest('[data-stop]'))return;
    if(el.tagName==='BUTTON')e.preventDefault();
    runAction(el).catch(error=>toast(message(error),true));
  });

  document.addEventListener('input',e=>{
    const target=e.target;
    if(target.id==='picker-search'){state.pickerSearch=target.value;filterPicker(target.value);}
    if(target.id==='student-filter'){state.filter=target.value;$$('.data-table tbody tr').forEach(tr=>{tr.style.display=tr.textContent.toLowerCase().includes(state.filter.toLowerCase())?'':'none';});}
    if(target.id==='result-filter'){state.resultSearch=target.value;$$('.data-table tbody tr').forEach(tr=>{tr.style.display=tr.textContent.toLowerCase().includes(state.resultSearch.toLowerCase())?'':'none';});}
    if(target.id==='bank-filter'){state.bankSearch=target.value;$$('.question-table tbody tr').forEach(tr=>{tr.style.display=tr.textContent.toLowerCase().includes(state.bankSearch.toLowerCase())?'':'none';});}
    if(target.closest('#exam-create-form')){draftFromForm($('#exam-create-form'),state.examDraft);if(target.name==='assignmentsText')$('#assignment-preview-wrap').innerHTML=assignmentPreview(target.value,listLabels(state.examDraft.set_count));}
    if(target.closest('#practice-form'))draftFromForm($('#practice-form'),state.practiceDraft);
  });
  document.addEventListener('change',async e=>{
    const t=e.target;
    try{
      if(t.id==='result-exam-select'){state.resultExamId=t.value;state.resultSearch='';state.resultStudent=null;state.resultsData=await api(`/api/v3/teacher/exams/${encodeURIComponent(t.value)}/results`);render();return;}
      if(t.id==='assignment-file'&&t.files?.[0]){const file=t.files[0];const contents=await file.text();const cleaned=contents.replace(/^\ufeff/,'').trim();state.examDraft.assignmentsText=cleaned;const field=$('[name="assignmentsText"]');if(field)field.value=cleaned;$('#assignment-preview-wrap').innerHTML=assignmentPreview(cleaned,listLabels(state.examDraft.set_count));toast('Roll numbers imported.');return;}
      if(t.id==='question-import'&&t.files?.[0]){const questions=JSON.parse(await t.files[0].text());if(!Array.isArray(questions))throw new Error('Import file must contain an array of questions.');const output=await post('/api/v3/teacher/questions/import',questions);state.bank=await api('/api/v3/teacher/questions');state.catalog=null;await loadCatalog();render();toast(`${output.imported} questions imported.`);return;}
      if(t.closest('#practice-form')&&['subject','topic','question_count'].includes(t.name)){
        draftFromForm($('#practice-form'),state.practiceDraft);if(t.name==='subject'){state.practiceDraft.topic='';state.practiceSelected.clear();}if(t.name==='topic')state.practiceSelected.clear();render();return;}
      if(t.closest('#exam-create-form')&&['subject','topic','set_count','question_count'].includes(t.name)){
        draftFromForm($('#exam-create-form'),state.examDraft);if(t.name==='subject'){state.examDraft.topic='';state.poolSelected.clear();state.manualSets={};}
        if(t.name==='topic'){state.poolSelected.clear();state.manualSets={};}
        render();return;}
    }catch(error){toast(message(error),true);}
  });

  document.addEventListener('submit',async e=>{
    const form=e.target;if(!form.id)return;e.preventDefault();
    const formData=new FormData(form), d=Object.fromEntries(formData.entries());
    const submitButton=$('[type="submit"]',form);
    if(submitButton){submitButton.disabled=true;submitButton.classList.add('is-working');}
    try{
      if(form.id==='login-form'){
        const out=await api('/api/v3/auth/login',{method:'POST',body:JSON.stringify({role:state.roleChoice,identifier:d.identifier,password:d.password})});
        state.user=out.user;state.csrf=out.csrf_token;state.page='dashboard';state.catalog=null;await refreshPage();render();
      }
      if(form.id==='practice-form'){
        draftFromForm(form,state.practiceDraft);const draft=state.practiceDraft,manual=draft.mode==='manual';
        if(manual&&state.practiceSelected.size!==Number(draft.question_count))throw new Error(`Choose exactly ${draft.question_count} questions.`);
        const out=await post('/api/v3/student/practice',{subject:draft.subject,topic:draft.topic,question_count:Number(draft.question_count),duration_minutes:Number(draft.duration_minutes),question_ids:manual?[...state.practiceSelected]:[]});
        await openAttempt(out.attempt_id);toast('Test successfully saved.');
      }
      if(form.id==='student-form'){
        const id=d.student_id;
        if(id){const payload={name:d.name,roll_number:d.roll_number};if(d.password)payload.password=d.password;await patch(`/api/v3/teacher/students/${encodeURIComponent(id)}`,payload);toast('Student account updated.');}
        else{await post('/api/v3/teacher/students',{name:d.name,roll_number:d.roll_number,password:d.password});toast('Student account created.');}
        state.students=await api('/api/v3/teacher/students');state.editStudentId='';render();
      }
      if(form.id==='exam-create-form'){
        draftFromForm(form,state.examDraft);const f=state.examDraft;
        const sets=listLabels(f.set_count);
        const assignments=parseRolls(f.assignmentsText);
        if(!assignments.length)throw new Error('Enter at least one student roll number.');
        if(f.selection_mode==='manual'&&sets.some(s=>(state.manualSets[s]?.size||0)!==Number(f.question_count)))throw new Error('Choose exactly the required questions for every paper set.');
        const date=new Date(f.scheduled_at);if(isNaN(date.getTime()))throw new Error('Select a valid examination date and time.');
        const payload={name:f.name,subject:f.subject,topic:f.topic,question_count:Number(f.question_count),duration_minutes:Number(f.duration_minutes),
          marks_per_question:Number(f.marks_per_question),negative_marks:Number(f.negative_marks),scheduled_at:date.toISOString(),set_count:Number(f.set_count),
          selection_mode:f.selection_mode,question_pool_ids:f.selection_mode==='automatic'?[...state.poolSelected]:[],
          sets:f.selection_mode==='manual'?sets.map(s=>({label:s,question_ids:[...state.manualSets[s]]})):[],assignments};
        await post('/api/v3/teacher/exams',payload);
        state.examDraft={name:'',subject:f.subject,topic:'',question_count:5,duration_minutes:30,marks_per_question:1,negative_marks:0,set_count:2,scheduled_at:localTime(),selection_mode:'automatic',assignmentsText:''};
        state.poolSelected.clear();state.manualSets={};await navigate('exams');toast('Test successfully saved.');
      }
      if(form.id==='assign-extra-form'){
        await post(`/api/v3/teacher/exams/${encodeURIComponent(state.selectedExamId)}/assignments`,{assignments:parseRolls(d.assignments)});
        state.examDetail=await api('/api/v3/teacher/exams/'+encodeURIComponent(state.selectedExamId));render();toast('Assignments saved.');
      }
      if(form.id==='question-form'){
        const values={subject:d.subject,topic:d.topic,difficulty:d.difficulty,question_type:d.question_type,text:d.text,correct_option:d.correct_option,
          wrong_options:d.wrong_options.split(/\r?\n/).map(x=>x.trim()).filter(Boolean)};
        await post('/api/v3/teacher/questions',values);state.bank=await api('/api/v3/teacher/questions');state.catalog=null;await loadCatalog();state.showQuestionForm=false;render();toast('Question added to bank.');
      }
      if(form.id==='password-form'){
        await post('/api/v3/auth/password',{old_password:d.old_password,new_password:d.new_password});form.reset();toast('Password updated.');
      }
    }catch(error){toast(message(error),true);}
    finally{if(submitButton&&submitButton.isConnected){submitButton.disabled=false;submitButton.classList.remove('is-working');}}
  });

  async function start(){
    try{const out=await api('/api/v3/auth/me');state.user=out.user;state.csrf=out.csrf_token;await refreshPage();}
    catch(e){state.user=null;state.csrf='';}
    render();
  }
  start();
})();
