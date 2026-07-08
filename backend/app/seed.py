from sqlalchemy.orm import Session

from .database import Base, engine
from .models import Company, StrategicIssue, Person, Decision


def seed_data(db: Session) -> None:
    if db.query(Company).count():
        return

    companies = [
        Company(
            name="PEC",
            description="MEP, Fire, and Structural engineering consulting firm.",
            leadership=["CEO"],
            strategic_issues=["Increase sales", "Improve PM quality", "Improve client retention", "Buyer diligence", "AI adoption"],
            projects=["PM Quality Initiative"],
            people=["Julio"],
            kpis=["Sales pipeline", "PM quality score"],
            decisions=["Julio promotion"],
            meetings=["Leadership review"],
        ),
        Company(
            name="RYSE Wellness",
            description="High-acuity residential mental health treatment center.",
            leadership=["CEO"],
            strategic_issues=["Increase census", "Improve admissions", "Reduce overtime", "Strengthen clinical operations", "Improve staff accountability", "Compliance readiness"],
            projects=["Admissions workflow"],
            people=["Admissions lead"],
            kpis=["Census", "OT hours"],
            decisions=[],
            meetings=[],
        ),
        Company(
            name="EverPole",
            description="Utility pole reinforcement product/company.",
            leadership=["CEO"],
            strategic_issues=["GTM strategy", "Distributor network", "Manufacturing cost", "Utility adoption", "Product improvements"],
            projects=["Distributor expansion"],
            people=[],
            kpis=["Distributor count"],
            decisions=[],
            meetings=[],
        ),
        Company(
            name="MyndLog",
            description="Personal journaling/logging app.",
            leadership=["Founder"],
            strategic_issues=["Linux migration", "AI journaling", "Privacy and backup strategy"],
            projects=["Platform migration"],
            people=[],
            kpis=["Migration progress"],
            decisions=[],
            meetings=[],
        ),
    ]
    db.add_all(companies)

    issues = [
        StrategicIssue(title="Increase PEC sales", company="PEC", owner="CEO", status="active"),
        StrategicIssue(title="Improve PM quality", company="PEC", owner="Julio", status="active"),
        StrategicIssue(title="Increase census", company="RYSE Wellness", owner="Ops Lead", status="active"),
        StrategicIssue(title="GTM strategy", company="EverPole", owner="CEO", status="active"),
    ]
    db.add_all(issues)

    person = Person(name="Julio", company="PEC", role="Project Manager", responsibilities=["PM quality", "high-priority clients"], current_priorities=["Improve PM quality"], strengths=["Execution", "Client delivery"], concerns=["Quality consistency"])
    db.add(person)

    decision = Decision(
        title="Julio promotion and pay increase",
        company="PEC",
        date="2026-07-07",
        context="Julio assumed responsibility for PM quality and high-priority clients.",
        options_considered=["Maintain current pay", "Increase pay and broaden scope"],
        final_decision="Increase pay from $14.42/hr to $17.50/hr and expand responsibilities.",
        reasoning="Recognize growth and align incentives with expanded ownership.",
        expected_outcome="Improved PM quality and stronger client delivery.",
        review_date="2026-10-07",
        linked_people=["Julio"],
        linked_projects=["PM Quality Initiative"],
        linked_strategic_issues=["Improve PM quality"],
    )
    db.add(decision)

    db.commit()


Base.metadata.create_all(bind=engine)
