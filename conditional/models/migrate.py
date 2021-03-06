from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from conditional import db
from conditional.models import models, old_models as zoo
import flask_migrate

# pylint: skip-file

old_engine = None
zoo_session = None


# Takes in param of SqlAlchemy Database Connection String
def free_the_zoo(zoo_url):

    confirm = str(input('Are you sure you want to clear and re-migrate the database? (y/N): ')).strip()
    if confirm == 'y':
        init_zoo_db(zoo_url)
        
        if flask_migrate.current() is not None:
            flask_migrate.downgrade(tag='base')
            
        flask_migrate.upgrade()

        migrate_models()


# Connect to Zookeeper
def init_zoo_db(database_url):
    global old_engine, zoo_session
    old_engine = create_engine(database_url, convert_unicode=True)
    zoo_session = scoped_session(sessionmaker(autocommit=False,
                                              autoflush=False,
                                              bind=old_engine))
    zoo.Base.metadata.create_all(bind=old_engine)


def id_to_committee(comm_id):
    committees = [
        'Evaluations',
        'Financial',
        'History',
        'House Improvements',
        'Opcomm',
        'R&D',
        'Social',
        'Social',
        'Chairman'
    ]
    return committees[comm_id]


def get_fid(name):
    from conditional.models.models import FreshmanAccount

    print(name)
    return FreshmanAccount.query.filter(FreshmanAccount.name == name).first().id


# Begin the Great Migration!
def migrate_models():
    print("BEGIN: freshman evals")
    # ==========

    tech_sems = {}

    freshman_evals = [
        {
            'username': f.username,
            'evalDate': f.voteDate,
            'projectStatus': f.freshProjPass,
            'signaturesMissed': f.numMissedSigs,
            'socialEvents': f.socEvents,
            'techSems': f.techSems,
            'comments': f.comments,
            'result': f.result
        } for f in zoo_session.query(zoo.FreshmanEval).all()]

    for f in freshman_evals:
        if not f['username'].startswith('f_'):
            # freshman who have completed packet and have a CSH account
            eval_data = models.FreshmanEvalData(f['username'], f['signaturesMissed'])

            # FIXME: Zookeeper was only pass/fail for freshman project not pending
            if f['projectStatus'] == 1:
                eval_data.freshman_project = 'Passed'

            eval_data.social_events = f['socialEvents']
            eval_data.other_notes = f['comments']
            eval_data.eval_date = f['evalDate']
            # TODO: conditional
            if f['result'] == "pass":
                eval_data.freshman_eval_result = "Passed"
            elif f['result'] == "fail":
                eval_data.freshman_eval_result = "Failed"
            else:
                eval_data.freshman_eval_result = "Pending"

            if f['techSems'] is not None:
                t_sems = f['techSems'].split(',')
                for sem in t_sems:
                    if sem not in tech_sems:
                        tech_sems[sem] = [f['username']]
                    else:
                        tech_sems[sem].append(f['username'])
            db.session.add(eval_data)
        else:
            # freshman not yet done with packet
            # TODO FIXME The FALSE dictates that they are not given onfloor
            # status
            account = models.FreshmanAccount(f['username'], False)
            account.eval_date = f['evalDate']
            if f['techSems'] is not None:
                t_sems = f['techSems'].split(',')
                for sem in t_sems:
                    if sem not in tech_sems:
                        tech_sems[sem] = [f['username']]
                    else:
                        tech_sems[sem].append(f['username'])
            db.session.add(account)

    print("tech sems")
    tech_sems.pop('', None)
    print(tech_sems)

    for t_sem in tech_sems:
        # TODO FIXME: Is there a timestamp we can migrate for seminars?
        from datetime import datetime
        sem = models.TechnicalSeminar(t_sem, datetime.now())
        db.session.add(sem)
        db.session.flush()
        db.session.refresh(sem)
        print(sem.__dict__)
        for m in tech_sems[t_sem]:
            if m.startswith("f_"):
                print(sem.id)
                a = models.FreshmanSeminarAttendance(get_fid(m), sem.id)
                db.session.add(a)
            else:
                a = models.MemberSeminarAttendance(m, sem.id)
                db.session.add(a)

    db.session.flush()

    print("END: freshman evals")
    # ==========

    print("BEGIN: migrate committee meeting attendance")
    # ==========
    c_meetings = [
        (
            m.meeting_date,
            m.committee_id
        ) for m in zoo_session.query(zoo.Attendance).all()]
    c_meetings = list(set(c_meetings))
    c_meetings = list(filter(lambda x: x[0] is not None, c_meetings))
    c_meetings.sort(key=lambda col: col[0])

    com_meetings = []
    for cm in c_meetings:
        m = models.CommitteeMeeting(id_to_committee(cm[1]), cm[0])
        if cm[0] is None:
            # fuck man
            continue
        db.session.add(m)
        db.session.flush()
        db.session.refresh(m)

        com_meetings.append(cm)

    c_meetings = [
        (
            m.username,
            (
                m.meeting_date,
                m.committee_id
            )
        ) for m in zoo_session.query(zoo.Attendance).all()]

    for cm in c_meetings:
        if cm[1][0] is None:
            # fuck man
            continue
        if cm[1][1] == 8:
            continue
        if cm[0].startswith('f_'):
            f = models.FreshmanCommitteeAttendance(
                get_fid(cm[0]),
                com_meetings.index(cm[1])
            )
            db.session.add(f)
        else:
            m = models.MemberCommitteeAttendance(cm[0], com_meetings.index(cm[1]) + 1)
            db.session.add(m)

    db.session.flush()

    print("END: migrate committee meeting attendance")
    # ==========

    print("BEGIN: migrate conditionals")
    # ==========

    condits = [
        {
            "uid": c.username,
            "desc": c.description,
            "deadline": c.deadline,
            "status": c.status
        } for c in zoo_session.query(zoo.Conditional).all()]

    for c in condits:
        condit = models.Conditional(c['uid'], c['desc'], c['deadline'])
        db.session.add(condit)

    print("END: migrate conditionals")

    # ==========

    print("BEGIN: house meetings")

    h_meetings = [hm.date for hm in zoo_session.query(zoo.HouseMeeting).all()]
    h_meetings = list(set(h_meetings))
    h_meetings.sort()
    print(h_meetings)

    house_meetings = {}
    for hm in h_meetings:
        m = models.HouseMeeting(hm)
        db.session.add(m)
        db.session.flush()
        db.session.refresh(m)
        house_meetings[hm.strftime("%Y-%m-%d")] = m.id

    print(house_meetings)

    hma = [
        {
            'uid': hm.username,
            'date': hm.date,
            'present': hm.present,
            'excused': hm.excused,
            'comments': hm.comments
        } for hm in zoo_session.query(zoo.HouseMeeting).all()]

    for a in hma:
        meeting_id = house_meetings[a['date'].strftime("%Y-%m-%d")]

        if a['present'] == 1:
            status = "Attended"
        elif a['excused'] == 1:
            status = "Excused"
        else:
            status = "Absent"

        excuse = a['comments']
        if a['uid'].startswith("f_"):
            # freshman
            fhma = models.FreshmanHouseMeetingAttendance(
                get_fid(a['uid']),
                meeting_id,
                excuse,
                status)
            db.session.add(fhma)
        else:
            # member
            mhma = models.MemberHouseMeetingAttendance(
                a['uid'],
                meeting_id,
                excuse,
                status)
            db.session.add(mhma)

    print("END: house meetings")

    # ==========

    print("BEGIN: Major Projects")

    projects = [
        {
            'username': mp.username,
            'name': mp.project_name,
            'description': mp.project_description,
            'status': mp.status
        } for mp in zoo_session.query(zoo.MajorProject).all()]

    for p in projects:
        mp = models.MajorProject(
            p['username'],
            p['name'],
            p['description']
        )

        if p['status'] == 'pass':
            mp.status = 'Passed'
        if p['status'] == 'fail':
            mp.status = 'Failed'

        db.session.add(mp)
    print("END: Major Projects")

    # ==========

    print("BEGIN: ON FLOOR")
    import conditional.util.ldap as ldap
    from datetime import datetime
    members = [m['uid'][0].decode('utf-8') for m in ldap.ldap_get_onfloor_members()]
    for m in members:
        db.session.add(models.OnFloorStatusAssigned(m, datetime.now()))
    print("END: ON FLOOR")

    print("BEGIN: SPRING EVALS")
    members = [m['uid'][0].decode('utf-8') for m in ldap.ldap_get_active_members()]
    for m in members:
        db.session.add(models.SpringEval(m))
    print("END: SPRING EVALS")
    print("BEGIN: Housing Evals")
    hevals = [
        {
            'username': he.username,
            'social_attended': he.social_attended,
            'social_hosted': he.social_hosted,
            'seminars_attended': he.seminars_attended,
            'seminars_hosted': he.seminars_hosted,
            'projects': he.projects,
            'comments': he.comments
        } for he in zoo_session.query(zoo.WinterEval).all()]

    for he in hevals:
        db.session.add(
            models.HousingEvalsSubmission(
                he['username'],
                he['social_attended'],
                he['social_hosted'],
                he['seminars_attended'],
                he['seminars_hosted'],
                he['projects'],
                he['comments']))
    print("END: Housing Evals")

    # Default EvalDB Settings
    db.session.add(models.EvalSettings())

    db.session.flush()
    db.session.commit()
