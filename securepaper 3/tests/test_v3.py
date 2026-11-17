"""Version 3 regression suite for authentication, assignments, timing and bank integrity."""
from __future__ import annotations

from datetime import timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from backend import main

PASSWORD = 'TeacherSecure!123'


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'securepaper.db')
    monkeypatch.setenv('SECUREPAPER_TEACHER_PASSWORD', PASSWORD)
    monkeypatch.setenv('SECUREPAPER_TEACHER_EMAIL', 'teacher@school.test')
    with TestClient(main.app) as client:
        yield client, monkeypatch


def teacher(client):
    response = client.post('/api/v3/auth/login', json={'role':'teacher','identifier':'teacher@school.test','password':PASSWORD})
    assert response.status_code == 200, response.text
    return {'X-CSRF-Token':response.json()['csrf_token']}


def add_students(client, headers, count=2):
    for i in range(count):
        response = client.post('/api/v3/teacher/students',json={'name':f'Student {i+1}',
            'roll_number':str(101+i),'password':'studentpass99'},headers=headers)
        assert response.status_code == 201, response.text


def login_student(app, roll):
    client = TestClient(app)
    response = client.post('/api/v3/auth/login',json={'role':'student','identifier':str(roll),'password':'studentpass99'})
    assert response.status_code == 200, response.text
    return client,{'X-CSRF-Token':response.json()['csrf_token']}


def create_exam(client, headers, **override):
    payload={'name':'Semester Electrical Exam','subject':'Electrical','topic':'',
      'question_count':4,'duration_minutes':20,'marks_per_question':2,
      'negative_marks':0.5,'scheduled_at':main.stamp(main.now()+timedelta(minutes=3)),
      'set_count':2,'selection_mode':'automatic',
      'assignments':[{'roll_number':'101','set_label':'A'},{'roll_number':'102','set_label':'B'}]}
    payload.update(override)
    response=client.post('/api/v3/teacher/exams',json=payload,headers=headers)
    assert response.status_code==201,response.text
    return response.json()['exam_id'], payload


def test_existing_bank_auth_and_login(env):
    client,_=env
    assert client.get('/api/health').json()['version']=='3'
    assert client.get('/api/v3/catalog').status_code==401
    assert client.get('/api/v3/teacher/questions').status_code==401
    h=teacher(client)
    bank=client.get('/api/v3/teacher/questions').json()
    assert len(bank)==90
    assert len({q['subject'] for q in bank})==5
    assert all(sum(o['is_correct'] for o in q['options'])==1 and sum(not o['is_correct'] for o in q['options'])>=3 for q in bank)
    assert client.post('/api/v3/teacher/students',json={'name':'A Student','roll_number':'201','password':'password123'}).status_code==403
    assert client.get('/api/sessions/someone').status_code==404
    assert client.get('/api/admin/questions',headers={'X-Admin-Key':'demo1234'}).status_code==404
    assert client.get('/static/styles.css').status_code==200
    assert 'SecurePaper' in client.get('/').text
    assert client.post('/api/v3/auth/logout',headers=h).status_code==200
    assert client.get('/api/v3/catalog').status_code==401


def test_unique_student_roll_and_deactivation(env):
    client,_=env
    h=teacher(client)
    add_students(client,h,1)
    conflict=client.post('/api/v3/teacher/students',json={'name':'Duplicate','roll_number':'101','password':'password123'},headers=h)
    assert conflict.status_code==409
    person=client.get('/api/v3/teacher/students').json()[0]
    student_client,sh=login_student(main.app,101)
    assert student_client.get('/api/v3/student/dashboard').status_code==200
    update=client.patch(f"/api/v3/teacher/students/{person['id']}",json={'name':'Renamed Student','roll_number':'101A','password':'newPassword42'},headers=h)
    assert update.status_code==200,update.text
    assert student_client.get('/api/v3/student/dashboard').status_code==401  # password reset revokes sessions
    new=student_client.post('/api/v3/auth/login',json={'role':'student','identifier':'101A','password':'newPassword42'})
    assert new.status_code==200
    assert client.patch(f"/api/v3/teacher/students/{person['id']}",json={'active':False},headers=h).status_code==200
    assert student_client.get('/api/v3/student/dashboard').status_code==401
    assert student_client.post('/api/v3/auth/login',json={'role':'student','identifier':'101A','password':'newPassword42'}).status_code==401


def test_student_practice_four_options_review_and_isolation(env):
    client,_=env
    h=teacher(client)
    add_students(client,h)
    alice,sh=login_student(main.app,101)
    bob,bh=login_student(main.app,102)
    assert alice.get('/api/v3/teacher/students').status_code==403
    create=alice.post('/api/v3/student/practice',json={'subject':'Chemistry','topic':'',
              'question_count':5,'duration_minutes':15},headers=sh)
    assert create.status_code==201,create.text
    assert create.json()['message']=='Test successfully saved.'
    aid=create.json()['attempt_id']
    attempt=alice.get('/api/v3/student/attempts/'+aid).json()
    assert len(attempt['questions'])==5
    assert all(len(q['options'])==4 for q in attempt['questions'])
    assert 'is_correct' not in str(attempt)
    q=attempt['questions'][0];option=q['options'][0]['id']
    assert alice.post(f'/api/v3/student/attempts/{aid}/answer',json={'question_id':q['id'],'option_id':option},headers=sh).status_code==200
    assert bob.get('/api/v3/student/attempts/'+aid).status_code==404
    assert bob.get('/api/v3/student/results/'+aid).status_code==404
    assert bob.post(f'/api/v3/student/attempts/{aid}/submit',headers=bh,json={}).status_code==404
    submitted=alice.post(f'/api/v3/student/attempts/{aid}/submit',headers=sh,json={})
    assert submitted.status_code==200,submitted.text
    assert submitted.json()['status']=='submitted' and len(submitted.json()['review'])==5
    assert alice.post(f'/api/v3/student/attempts/{aid}/answer',json={'question_id':q['id'],'option_id':option},headers=sh).status_code==409


def test_teacher_assignments_lock_distinct_sets_and_expiry(env):
    client,monkeypatch=env
    h=teacher(client)
    add_students(client,h)
    exam_id,payload=create_exam(client,h)
    detail=client.get(f'/api/v3/teacher/exams/{exam_id}').json()
    assert [s['label'] for s in detail['sets']]==['A','B']
    assert set(detail['sets'][0]['question_ids']).isdisjoint(set(detail['sets'][1]['question_ids']))
    alice,ah=login_student(main.app,101)
    bob,bh=login_student(main.app,102)
    x=alice.get('/api/v3/student/dashboard').json()['assignments'][0]
    y=bob.get('/api/v3/student/dashboard').json()['assignments'][0]
    assert x['paper_set']=='A' and y['paper_set']=='B'
    assert x['status']=='Upcoming'
    assert 'questions' not in str(alice.get(f"/api/v3/student/assignments/{x['assignment_id']}").json())
    assert alice.post(f"/api/v3/student/assignments/{x['assignment_id']}/start",headers=ah,json={}).status_code==423
    assert bob.get(f"/api/v3/student/assignments/{x['assignment_id']}").status_code==404
    assert alice.get(f'/api/v3/teacher/exams/{exam_id}').status_code==403
    scheduled=main.parsed(payload['scheduled_at'])
    monkeypatch.setattr(main,'now',lambda:scheduled+timedelta(seconds=5))
    start=alice.post(f"/api/v3/student/assignments/{x['assignment_id']}/start",headers=ah,json={})
    assert start.status_code==200,start.text
    aid=start.json()['attempt_id']
    active=alice.get('/api/v3/student/attempts/'+aid).json()
    assert active['status']=='active' and len(active['questions'])==4
    assert 'correct_text' not in str(active)
    assert main.parsed(active['deadline_at'])==scheduled+timedelta(minutes=20)
    # Submission can be requested only by the assigned account.
    assert bob.post(f'/api/v3/student/attempts/{aid}/submit',headers=bh,json={}).status_code==404
    # Expired attempts are finalized server-side, even if no browser submits.
    monkeypatch.setattr(main,'now',lambda:scheduled+timedelta(minutes=21))
    expired=alice.get('/api/v3/student/attempts/'+aid).json()
    assert expired['status']=='submitted' and expired['review']
    assert alice.post(f'/api/v3/student/attempts/{aid}/answer',headers=ah,
                      json={'question_id':active['questions'][0]['id'],'option_id':active['questions'][0]['options'][0]['id']}).status_code==409
    assert bob.post(f"/api/v3/student/assignments/{y['assignment_id']}/start",headers=bh,json={}).status_code==409


def test_teacher_results_export_csv_excel_and_manual_sets(env):
    client,monkeypatch=env
    h=teacher(client)
    add_students(client,h)
    qs=[q for q in client.get('/api/v3/teacher/questions').json() if q['subject']=='Physics']
    scheduled=main.now()+timedelta(minutes=2)
    eid,_=create_exam(client,h,name='Physics Midterm',subject='Physics',question_count=3,
         set_count=2,selection_mode='manual',scheduled_at=main.stamp(scheduled),
         sets=[{'label':'A','question_ids':[q['id'] for q in qs[:3]]},
               {'label':'B','question_ids':[q['id'] for q in qs[3:6]]}])
    alice,ah=login_student(main.app,101)
    aid=alice.get('/api/v3/student/dashboard').json()['assignments'][0]['assignment_id']
    monkeypatch.setattr(main,'now',lambda:scheduled+timedelta(seconds=1))
    attempt_id=alice.post(f'/api/v3/student/assignments/{aid}/start',headers=ah,json={}).json()['attempt_id']
    question=alice.get('/api/v3/student/attempts/'+attempt_id).json()['questions'][0]
    with main.database() as c:
        right=c.execute('SELECT id FROM question_options WHERE question_id=? AND is_correct=1',(question['id'],)).fetchone()['id']
    # Options were chosen per student, so the stored correct answer is in the four choices.
    assert right in [option['id'] for option in question['options']]
    alice.post(f'/api/v3/student/attempts/{attempt_id}/answer',headers=ah,json={'question_id':question['id'],'option_id':right})
    result=alice.post(f'/api/v3/student/attempts/{attempt_id}/submit',headers=ah,json={}).json()
    assert result['score']==2 and result.get('review_available') is False
    report=client.get(f'/api/v3/teacher/exams/{eid}/results').json()
    assert report['summary']=={'total_assigned':2,'attempted':1,'not_attempted':1,'submitted':1}
    assert any(r['roll_number']=='101' and r['score']==2 for r in report['rows'])
    assert len(client.get(f"/api/v3/teacher/exams/{eid}/results/{client.get('/api/v3/teacher/students').json()[0]['id']}").json()['review'])==3
    csv_content=client.get(f'/api/v3/teacher/exams/{eid}/export?format=csv').content.decode('utf-8-sig')
    assert 'Roll number,Student name,Paper set' in csv_content and '101' in csv_content
    excel=client.get(f'/api/v3/teacher/exams/{eid}/export?format=xlsx')
    assert excel.status_code==200
    from openpyxl import load_workbook
    workbook=load_workbook(BytesIO(excel.content),read_only=True)
    assert workbook.active['A4'].value=='Roll number'
    assert workbook.active['A5'].value=='101'


def test_atomic_exam_rejects_unknown_roll_and_preserves_question_bank(env):
    client,_=env
    h=teacher(client)
    add_students(client,h,1)
    before=len(client.get('/api/v3/teacher/questions').json())
    invalid={'name':'Bad paper','subject':'Chemistry','question_count':3,'duration_minutes':5,
      'marks_per_question':1,'negative_marks':0,'scheduled_at':main.stamp(main.now()+timedelta(minutes=2)),
      'set_count':1,'assignments':[{'roll_number':'404'}]}
    failure=client.post('/api/v3/teacher/exams',json=invalid,headers=h)
    assert failure.status_code==422
    assert client.get('/api/v3/teacher/exams').json()==[]
    assert len(client.get('/api/v3/teacher/questions').json())==before
    sample={'subject':'Chemistry','topic':'Solutions','difficulty':'easy','question_type':'conceptual',
        'text':'Which solvent is most common in aqueous solutions?','correct_option':'Water',
        'wrong_options':['Petrol','Acetone','Mercury','Methane']}
    added=client.post('/api/v3/teacher/questions',json=sample,headers=h)
    assert added.status_code==201
    assert len(client.get('/api/v3/teacher/questions').json())==before+1
    assert client.patch(f"/api/v3/teacher/questions/{added.json()['id']}?active=false",headers=h).status_code==200
    assert len(client.get('/api/v3/questions').json())==before


def test_teacher_cannot_read_another_teacher_exams(env):
    client,_=env
    h=teacher(client)
    add_students(client,h)
    eid,_=create_exam(client,h)
    with main.database() as c:
        person_id=main.uid()
        c.execute("INSERT INTO users(id,role,name,email,password_hash,created_at,updated_at) VALUES(?, 'teacher',?,?,?,?,?)",
                  (person_id,'Second Teacher','second@school.test',main.hash_password('secondSecure123'),main.stamp(),main.stamp()))
    other=TestClient(main.app)
    logged=other.post('/api/v3/auth/login',json={'role':'teacher','identifier':'second@school.test','password':'secondSecure123'})
    assert logged.status_code==200
    header={'X-CSRF-Token':logged.json()['csrf_token']}
    assert other.get(f'/api/v3/teacher/exams/{eid}').status_code==404
    assert other.get(f'/api/v3/teacher/exams/{eid}/results').status_code==404
    assert other.get(f'/api/v3/teacher/exams/{eid}/export').status_code==404
    assert other.post(f'/api/v3/teacher/exams/{eid}/assignments',headers=header,
                json={'assignments':[{'roll_number':'101'}]}).status_code==404
    assert other.get('/api/v3/teacher/students').json()==[]


def test_bank_and_students_preserved_on_restart(env):
    client,_=env
    h=teacher(client)
    add_students(client,h,1)
    with main.database() as c:
        before=(c.execute('SELECT COUNT(*) FROM questions').fetchone()[0],
                c.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0])
    main.init_db()
    with main.database() as c:
        after=(c.execute('SELECT COUNT(*) FROM questions').fetchone()[0],
               c.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0])
    assert before==after==(90,1)


def test_questions_in_future_exams_are_not_disclosed_in_student_practice(env):
    client,_=env
    h=teacher(client)
    add_students(client,h)
    eid,_=create_exam(client,h)
    reserved={q for paper in client.get(f'/api/v3/teacher/exams/{eid}').json()['sets'] for q in paper['question_ids']}
    assert len(reserved)==8
    alice,ah=login_student(main.app,101)
    student_questions=alice.get('/api/v3/questions?subject=Electrical').json()
    assert not reserved.intersection({q['id'] for q in student_questions})
    teacher_questions=client.get('/api/v3/teacher/questions?subject=Electrical').json()
    assert reserved.issubset({q['id'] for q in teacher_questions})
    manual=alice.post('/api/v3/student/practice',headers=ah,
                      json={'subject':'Electrical','question_count':1,'duration_minutes':5,
                            'question_ids':[next(iter(reserved))]})
    assert manual.status_code==422
    practice=alice.post('/api/v3/student/practice',headers=ah,
                        json={'subject':'Electrical','question_count':5,'duration_minutes':5})
    assert practice.status_code==201,practice.text
    created=alice.get('/api/v3/student/attempts/'+practice.json()['attempt_id']).json()
    assert not reserved.intersection({q['id'] for q in created['questions']})


def test_teacher_negative_marking_and_result_release_window(env):
    client,monkeypatch=env
    h=teacher(client)
    add_students(client,h)
    exam_id,payload=create_exam(client,h,question_count=2,marks_per_question=3,negative_marks=1)
    alice,ah=login_student(main.app,101)
    assignment=alice.get('/api/v3/student/dashboard').json()['assignments'][0]
    start=main.parsed(payload['scheduled_at'])
    monkeypatch.setattr(main,'now',lambda:start+timedelta(seconds=1))
    result=alice.post(f"/api/v3/student/assignments/{assignment['assignment_id']}/start",headers=ah,json={})
    aid=result.json()['attempt_id']
    qs=alice.get('/api/v3/student/attempts/'+aid).json()['questions']
    with main.database() as c:
        correct=c.execute('SELECT id FROM question_options WHERE question_id=? AND is_correct=1',(qs[0]['id'],)).fetchone()['id']
        wrong=c.execute('''SELECT ao.option_id FROM v3_attempt_options ao JOIN question_options qo ON qo.id=ao.option_id
                          WHERE ao.attempt_id=? AND ao.question_id=? AND qo.is_correct=0 LIMIT 1''',(aid,qs[1]['id'])).fetchone()['option_id']
    assert alice.post(f'/api/v3/student/attempts/{aid}/answer',headers=ah,
                     json={'question_id':qs[0]['id'],'option_id':correct}).status_code==200
    assert alice.post(f'/api/v3/student/attempts/{aid}/answer',headers=ah,
                     json={'question_id':qs[1]['id'],'option_id':wrong}).status_code==200
    submitted=alice.post(f'/api/v3/student/attempts/{aid}/submit',headers=ah,json={}).json()
    assert submitted['score']==2.0
    assert submitted.get('review_available') is False and 'review' not in submitted
    assert 'review' in client.get(f'/api/v3/teacher/exams/{exam_id}/results/{client.get("/api/v3/teacher/students").json()[0]["id"]}').json()
    monkeypatch.setattr(main,'now',lambda:start+timedelta(minutes=21))
    released=alice.get('/api/v3/student/results/'+aid).json()
    assert len(released['review'])==2


def test_extra_assignments_validate_and_cannot_change_after_start(env):
    client,monkeypatch=env
    h=teacher(client)
    add_students(client,h,3)
    eid,payload=create_exam(client,h)
    added=client.post(f'/api/v3/teacher/exams/{eid}/assignments',headers=h,
                 json={'assignments':[{'roll_number':'103','set_label':'B'}]})
    assert added.status_code==200
    details=client.get(f'/api/v3/teacher/exams/{eid}').json()
    assert any(x['roll_number']=='103' and x['paper_set']=='B' for x in details['assignments'])
    before=len(details['assignments'])
    bad=client.post(f'/api/v3/teacher/exams/{eid}/assignments',headers=h,
                 json={'assignments':[{'roll_number':'UNKNOWN','set_label':'A'}]})
    assert bad.status_code==422
    assert len(client.get(f'/api/v3/teacher/exams/{eid}').json()['assignments'])==before
    monkeypatch.setattr(main,'now',lambda:main.parsed(payload['scheduled_at'])+timedelta(seconds=2))
    assert client.post(f'/api/v3/teacher/exams/{eid}/assignments',headers=h,
                 json={'assignments':[{'roll_number':'103','set_label':'A'}]}).status_code==409


def test_csrf_cookie_security_and_question_import_rollback(env):
    client,_=env
    h=teacher(client)
    login=client.get('/api/v3/auth/me')
    assert 'csrf_token' in login.json()
    no_csrf=client.post('/api/v3/teacher/students',json={'name':'Not Authorized','roll_number':'333','password':'12345678'})
    assert no_csrf.status_code==403
    bad_csrf=client.post('/api/v3/teacher/students',headers={'X-CSRF-Token':'bad'},
              json={'name':'Not Authorized','roll_number':'333','password':'12345678'})
    assert bad_csrf.status_code==403
    original=client.get('/api/v3/teacher/questions').json()
    question={'subject':'Physics','topic':'Gravity','difficulty':'easy','question_type':'conceptual',
               'text':'Which direction does gravity normally act near Earth?','correct_option':'Toward Earth',
               'wrong_options':['Away from Earth','East','West']}
    duplicated=client.post('/api/v3/teacher/questions/import',headers=h,json=[question,question])
    assert duplicated.status_code==422
    assert len(client.get('/api/v3/teacher/questions').json())==len(original)
    # A spoofed cross-origin login cannot create a browser session.
    other=TestClient(main.app)
    bad=other.post('/api/v3/auth/login',headers={'Origin':'https://outside.invalid'},
        json={'role':'teacher','identifier':'teacher@school.test','password':PASSWORD})
    assert bad.status_code==403
    # HTTPS terminates at Render's proxy, and the cookie still receives the Secure flag.
    secure=other.post('/api/v3/auth/login',headers={'X-Forwarded-Proto':'https'},
        json={'role':'teacher','identifier':'teacher@school.test','password':PASSWORD})
    assert secure.status_code==200
    assert 'secure' in secure.headers['set-cookie'].lower()


def test_migrates_real_v2_database_preserving_existing_rows(tmp_path,monkeypatch):
    import shutil
    from pathlib import Path
    sample=Path(__file__).resolve().parents[1]/'legacy'/'version2'/'securepaper_v2_bank.db'
    new_db=tmp_path/'securepaper.db'
    shutil.copy2(sample,new_db)
    monkeypatch.setattr(main,'DATA_DIR',tmp_path)
    monkeypatch.setattr(main,'DB_PATH',new_db)
    monkeypatch.setenv('SECUREPAPER_TEACHER_PASSWORD',PASSWORD)
    with main.database() as c:
        before=c.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
        old_sessions=c.execute('SELECT COUNT(*) FROM exam_sessions').fetchone()[0]
    main.init_db()
    with main.database() as c:
        assert c.execute('SELECT COUNT(*) FROM questions').fetchone()[0]==before
        assert c.execute('SELECT COUNT(*) FROM exam_sessions').fetchone()[0]==old_sessions
        assert c.execute("SELECT COUNT(*) FROM users WHERE role='teacher'").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM v3_exams").fetchone()[0]==0
