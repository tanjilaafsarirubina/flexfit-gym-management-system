import os
from datetime import datetime, timedelta
from app import app, db
from gym_models import (
    User, TrainerProfile, MembershipPlan, UserMembership,
    GymClass, ClassBooking, WorkoutLog, ExerciseVideo, MealPlan,
    Feedback, CoachingSession, Payment, local_now, local_today
)

def seed_database():
    with app.app_context():
        db.drop_all()
        db.create_all()

        print("Seeding database with full features, real accounts, reviews, and evidence-based nutrition plans...")

        monthly = MembershipPlan(
            name="Monthly Access",
            price=29.99,
            duration_days=30,
            features="Access to gym floor, standard group classes, locker room, hydration station."
        )
        quarterly = MembershipPlan(
            name="Quarterly Pro",
            price=79.99,
            duration_days=90,
            features="Access to all gym facilities, priority class booking, 1 free trainer consultation, video library."
        )
        annual = MembershipPlan(
            name="Annual Gold",
            price=249.99,
            duration_days=365,
            features="Unlimited VIP access, free video library, 2 trainer sessions/month, custom meal plan, spa access."
        )
        db.session.add_all([monthly, quarterly, annual])
        db.session.commit()

        member1 = User(
            full_name="Tanjila Afsari Rubina",
            email="tanjila@flexfit.com",
            phone="+8801711000001",
            role="member"
        )
        member1.set_password("password123")

        member2 = User(
            full_name="Rahim Chowdhury",
            email="rahim@flexfit.com",
            phone="+8801711000002",
            role="member"
        )
        member2.set_password("password123")

        member3 = User(
            full_name="Nusrat Jahan",
            email="nusrat@flexfit.com",
            phone="+8801711000003",
            role="member"
        )
        member3.set_password("password123")

        trainer1 = User(
            full_name="Sarah Ahmed",
            email="sarah@flexfit.com",
            phone="+8801811000001",
            role="trainer"
        )
        trainer1.set_password("password123")

        trainer2 = User(
            full_name="Tanvir Hasan",
            email="tanvir@flexfit.com",
            phone="+8801811000002",
            role="trainer"
        )
        trainer2.set_password("password123")

        trainer3 = User(
            full_name="Farhan Kabir",
            email="farhan@flexfit.com",
            phone="+8801811000003",
            role="trainer"
        )
        trainer3.set_password("password123")

        admin_user = User(
            full_name="Alex Morgan",
            email="admin@flexfit.com",
            phone="+8801511000001",
            role="admin"
        )
        admin_user.set_password("admin123")

        db.session.add_all([member1, member2, member3, trainer1, trainer2, trainer3, admin_user])
        db.session.commit()

        profile_sarah = TrainerProfile(
            user_id=trainer1.id,
            bio="Certified Yoga & Mindfulness Specialist with 6+ years of coaching experience. Passionate about holistic flexibility, posture restoration, and core alignment.",
            specialization="Yoga & Core Mobility",
            hourly_rate=45.00,
            profile_image_url="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
        )
        profile_tanvir = TrainerProfile(
            user_id=trainer2.id,
            bio="Expert Strength & Hypertrophy Coach helping clients hit major compound PRs. Certified in progressive overload programming and functional powerlifting.",
            specialization="High Intensity Strength",
            hourly_rate=55.00,
            profile_image_url="https://images.unsplash.com/photo-1567013127542-490d757e51fc?w=400"
        )
        profile_farhan = TrainerProfile(
            user_id=trainer3.id,
            bio="High Energy HIIT & Endurance Coach specialized in Functional Metabolic Conditioning, athletic sprint intervals, and rapid cardiovascular transformations.",
            specialization="Cardio HIIT & Conditioning",
            hourly_rate=50.00,
            profile_image_url="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400"
        )
        db.session.add_all([profile_sarah, profile_tanvir, profile_farhan])
        db.session.commit()

        today = local_today()
        m1_plan = UserMembership(
            user_id=member1.id,
            plan_id=annual.id,
            start_date=today - timedelta(days=60),
            end_date=today + timedelta(days=305),
            status="active"
        )
        m2_plan = UserMembership(
            user_id=member2.id,
            plan_id=quarterly.id,
            start_date=today - timedelta(days=15),
            end_date=today + timedelta(days=75),
            status="active"
        )
        m3_plan = UserMembership(
            user_id=member3.id,
            plan_id=monthly.id,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=25),
            status="active"
        )
        db.session.add_all([m1_plan, m2_plan, m3_plan])
        db.session.add_all([
            Payment(user_id=member1.id, plan_name=annual.name, amount=annual.price, method="card",
                    transaction_id="VISA48213377", paid_at=local_now() - timedelta(days=60)),
            Payment(user_id=member2.id, plan_name=quarterly.name, amount=quarterly.price, method="bkash",
                    transaction_id="BKASH51730284", paid_at=local_now() - timedelta(days=15)),
            Payment(user_id=member3.id, plan_name=monthly.name, amount=monthly.price, method="nagad",
                    transaction_id="NAGAD90417652", paid_at=local_now() - timedelta(days=5)),
        ])
        db.session.commit()

        now = local_now()

        class_yoga1 = GymClass(
            trainer_id=profile_sarah.id,
            title="Power Yoga Flow",
            category="Yoga",
            start_time=now.replace(hour=17, minute=0, second=0),
            duration_mins=60,
            max_capacity=10
        )
        class_yoga2 = GymClass(
            trainer_id=profile_sarah.id,
            title="Morning Vinyasa Flow",
            category="Yoga",
            start_time=now + timedelta(days=1, hours=1),
            duration_mins=60,
            max_capacity=8
        )
        class_yoga3 = GymClass(
            trainer_id=profile_sarah.id,
            title="Sunset Flexibility & Core Alignment",
            category="Yoga",
            start_time=now + timedelta(days=3, hours=6),
            duration_mins=45,
            max_capacity=12
        )

        class_strength1 = GymClass(
            trainer_id=profile_tanvir.id,
            title="High Intensity Strength",
            category="Strength",
            start_time=now + timedelta(days=1, hours=2),
            duration_mins=45,
            max_capacity=12
        )
        class_strength2 = GymClass(
            trainer_id=profile_tanvir.id,
            title="Hypertrophy Chest & Arms Sculpt",
            category="Strength",
            start_time=now + timedelta(days=2, hours=3),
            duration_mins=50,
            max_capacity=10
        )
        class_strength3 = GymClass(
            trainer_id=profile_tanvir.id,
            title="Heavy Compound Deadlifts & Legs",
            category="Strength",
            start_time=now + timedelta(days=4, hours=2),
            duration_mins=60,
            max_capacity=8
        )

        class_cardio1 = GymClass(
            trainer_id=profile_farhan.id,
            title="Cardio HIIT & Conditioning",
            category="Cardio",
            start_time=now + timedelta(days=2, hours=4),
            duration_mins=50,
            max_capacity=15
        )
        class_cardio2 = GymClass(
            trainer_id=profile_farhan.id,
            title="Fat Burn Sprint Interval",
            category="Cardio",
            start_time=now + timedelta(days=3, hours=2),
            duration_mins=45,
            max_capacity=12
        )
        class_cardio3 = GymClass(
            trainer_id=profile_farhan.id,
            title="Metabolic Bodyweight Circuit",
            category="Cardio",
            start_time=now + timedelta(days=5, hours=5),
            duration_mins=40,
            max_capacity=15
        )

        db.session.add_all([
            class_yoga1, class_yoga2, class_yoga3,
            class_strength1, class_strength2, class_strength3,
            class_cardio1, class_cardio2, class_cardio3
        ])
        db.session.commit()

        booking1 = ClassBooking(user_id=member1.id, class_id=class_yoga1.id, status="booked", attended=False)
        booking2 = ClassBooking(user_id=member2.id, class_id=class_strength1.id, status="booked", attended=False)
        booking3 = ClassBooking(user_id=member3.id, class_id=class_cardio1.id, status="booked", attended=False)
        booking4 = ClassBooking(user_id=member2.id, class_id=class_yoga2.id, status="booked", attended=False)
        db.session.add_all([booking1, booking2, booking3, booking4])

        for _ in range(12):
            past_b = ClassBooking(user_id=member1.id, class_id=class_yoga1.id, status="completed", attended=True)
            db.session.add(past_b)

        for _ in range(5):
            past_b = ClassBooking(user_id=member2.id, class_id=class_strength1.id, status="completed", attended=True)
            db.session.add(past_b)

        for _ in range(3):
            past_b = ClassBooking(user_id=member3.id, class_id=class_cardio1.id, status="completed", attended=True)
            db.session.add(past_b)

        db.session.commit()

        log1 = WorkoutLog(user_id=member1.id, exercise_name="Barbell Deadlift", sets=3, reps=10, weight_kg=30.0, log_date=today - timedelta(days=2))
        log2 = WorkoutLog(user_id=member1.id, exercise_name="Dumbbell Squats", sets=4, reps=10, weight_kg=12.5, log_date=today - timedelta(days=1))
        log3 = WorkoutLog(user_id=member1.id, exercise_name="Overhead Shoulder Press", sets=2, reps=5, weight_kg=5.0, log_date=today)

        log4 = WorkoutLog(user_id=member2.id, exercise_name="Bench Press", sets=4, reps=8, weight_kg=70.0, log_date=today - timedelta(days=3))
        log5 = WorkoutLog(user_id=member2.id, exercise_name="Barbell Squats", sets=5, reps=5, weight_kg=100.0, log_date=today - timedelta(days=1))

        log6 = WorkoutLog(user_id=member3.id, exercise_name="Kettlebell Swings", sets=3, reps=15, weight_kg=16.0, log_date=today)

        db.session.add_all([log1, log2, log3, log4, log5, log6])

        cs1 = CoachingSession(
            client_id=member1.id,
            trainer_id=profile_sarah.id,
            session_time=now + timedelta(days=2, hours=3),
            notes="Focus on hip mobility and lower back posture alignment.",
            status="scheduled"
        )
        cs2 = CoachingSession(
            client_id=member2.id,
            trainer_id=profile_tanvir.id,
            session_time=now + timedelta(days=3, hours=5),
            notes="Bench press form analysis and 1RM progression strategy.",
            status="scheduled"
        )
        db.session.add_all([cs1, cs2])

        vid1 = ExerciseVideo(
            title="Full Body HIIT Fat Burn",
            category="Cardio",
            difficulty="Intermediate",
            video_url="https://www.youtube.com/embed/ml6cT4AZdqI",
            thumbnail_url="https://images.unsplash.com/photo-1518611012118-696072aa579a?w=500",
            description="High intensity interval circuit targeting full body fat oxidation and athletic cardio conditioning."
        )
        vid2 = ExerciseVideo(
            title="Core & Upper Body Strength",
            category="Strength",
            difficulty="Advanced",
            video_url="https://www.youtube.com/embed/gC_L9qAHVJ8",
            thumbnail_url="https://images.unsplash.com/photo-1581009146145-b5ef050c2e1e?w=500",
            description="Heavy compound lifting protocols focused on chest, back, shoulders, and core bracing."
        )
        vid3 = ExerciseVideo(
            title="Morning Flow & Mobility Yoga",
            category="Yoga",
            difficulty="Beginner",
            video_url="https://www.youtube.com/embed/v7AYKMP6rOE",
            thumbnail_url="https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=500",
            description="Calming morning flexibility sequences to open the thoracic spine, hamstrings, and hip flexors."
        )
        vid4 = ExerciseVideo(
            title="Sprint Interval Tabata Blast",
            category="Cardio",
            difficulty="Advanced",
            video_url="https://www.youtube.com/embed/cbKkB3POqaY",
            thumbnail_url="https://images.unsplash.com/photo-1434596922112-19c563067271?w=500",
            description="20 seconds on, 10 seconds off Tabata drills to push VO2 max and accelerate metabolic burn."
        )
        vid5 = ExerciseVideo(
            title="Dumbbell Hypertrophy Full Routine",
            category="Strength",
            difficulty="Intermediate",
            video_url="https://www.youtube.com/embed/eMjyvIQbn9M",
            thumbnail_url="https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=500",
            description="Targeted dumbbell hypertrophy work covering arms, shoulders, quads, and upper back."
        )
        vid6 = ExerciseVideo(
            title="Deep Restorative Yoga & Breathwork",
            category="Yoga",
            difficulty="Beginner",
            video_url="https://www.youtube.com/embed/sTANio_2E0Q",
            thumbnail_url="https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=500",
            description="Evening relaxation and parasympathetic breathing sequence to recover from heavy workouts."
        )
        db.session.add_all([vid1, vid2, vid3, vid4, vid5, vid6])

        meal1 = MealPlan(
            title="High-Protein Hypertrophy & Muscle Synthesis Protocol",
            goal="Muscle Gain",
            calories_per_day=2850,
            protein_g=195,
            carbs_g=340,
            fat_g=75,
            pdf_url="#",
            description="Evidence-based hypercaloric sports nutrition protocol designed per ISSN guidelines (2.0g protein/kg) to maximize muscle protein synthesis (MPS), maintain positive nitrogen balance, and fuel high-volume progressive overload training.",
            meal_breakdown="• Meal 1 - Power Breakfast (7:30 AM): 4 Whole Pasture Eggs + 2 Egg Whites, 100g Rolled Oats with 50g Blueberries, 15g Chia Seeds, and 1 scoop Whey Isolate (720 kcal, 52g Protein, 68g Carbs, 22g Fat)\n• Meal 2 - Mid-Morning Synthesis (11:00 AM): 250g 0% Fat Greek Yogurt with 30g Raw Almonds, 1 sliced Banana, and 1 tbsp Organic Honey (440 kcal, 36g Protein, 48g Carbs, 16g Fat)\n• Meal 3 - Pre-Training Complex Fuel (2:00 PM): 180g Grilled Chicken Breast, 220g Jasmine Rice, 100g Steamed Broccoli, and 1 tbsp Cold-Pressed Olive Oil (680 kcal, 48g Protein, 75g Carbs, 15g Fat)\n• Meal 4 - Post-Workout Anabolic Replenishment (5:30 PM): 50g Cream of Rice with 1.5 scoops Whey Isolate, 5g Creatine Monohydrate, and 1 diced Apple (390 kcal, 38g Protein, 65g Carbs, 3g Fat)\n• Meal 5 - Evening Recovery Dinner (8:30 PM): 200g Wild Atlantic Salmon Fillet, 250g Baked Sweet Potato, 150g Grilled Asparagus spears, and Mixed Greens salad (620 kcal, 45g Protein, 54g Carbs, 19g Fat)"
        )
        meal2 = MealPlan(
            title="Moderate-Deficit Metabolic Fat Loss & Muscle Sparing Protocol",
            goal="Weight Loss",
            calories_per_day=1950,
            protein_g=175,
            carbs_g=160,
            fat_g=65,
            pdf_url="#",
            description="Clinically structured caloric deficit (-500 kcal) with elevated protein distribution (2.2g–2.4g/kg) and low-glycemic complex carbohydrates to preserve lean contractile mass, stabilize blood glucose, and accelerate lipid oxidation.",
            meal_breakdown="• Meal 1 - Satiety & Metabolic Jumpstart (8:00 AM): 3 Whole Eggs + 3 Egg Whites scrambled with Baby Spinach, Half Hass Avocado (75g), and 1 slice Toasted Sprouted Ezekiel Bread (450 kcal, 38g Protein, 18g Carbs, 24g Fat)\n• Meal 2 - Lean Protein & Micronutrient Bowl (12:30 PM): 180g Extra-Lean Ground Turkey (93/7), 150g Quinoa, 100g Roasted Zucchini & Bell Peppers, and 1 tbsp Extra Virgin Olive Oil (520 kcal, 44g Protein, 42g Carbs, 18g Fat)\n• Meal 3 - Pre-Workout Energy & Fiber Booster (4:00 PM): 1 Medium Crisp Apple with 20g Natural Peanut Butter and 1 scoop Whey Protein Isolate mixed in water (290 kcal, 28g Protein, 28g Carbs, 10g Fat)\n• Meal 4 - Nighttime Sparing & Hormone Support (7:30 PM): 200g Pan-Seared Cod or Wild Halibut, 180g Steamed Cauliflower Mash, 100g Green Beans, and 15g Walnuts (450 kcal, 45g Protein, 22g Carbs, 13g Fat)\n• Pre-Sleep Micellar Casein (Optional): 25g Micellar Casein with Water (100 kcal, 20g Protein, 2g Carbs, 1g Fat)"
        )
        meal3 = MealPlan(
            title="Mediterranean Athletic Longevity & Energy Maintenance Regimen",
            goal="Maintenance",
            calories_per_day=2350,
            protein_g=160,
            carbs_g=260,
            fat_g=75,
            pdf_url="#",
            description="Cardiovascular and metabolic longevity blueprint centered around the Mediterranean dietary pattern: rich in polyphenols, monounsaturated lipids, wild seafood, whole grains, and leafy botanicals for sustained daily athletic output.",
            meal_breakdown="• Breakfast (8:00 AM): 2 Poached Pasture-Raised Eggs over Sourdough Toast (2 slices) with mashed Avocado, Cherry Tomatoes, and 1 cup Mixed Berries (510 kcal, 26g Protein, 55g Carbs, 21g Fat)\n• Lunch (1:00 PM): Mediterranean Tuna & Farro Bowl — 180g Solid White Albacore Tuna, 160g Cooked Farro, Kalamata Olives (30g), Diced Cucumbers, Crumbled Feta (25g), and Lemon Oregano Vinaigrette (630 kcal, 48g Protein, 62g Carbs, 22g Fat)\n• Afternoon Energy (4:30 PM): 200g Low-Fat Kefir or Greek Yogurt with 25g Raw Walnuts and 1 tsp Organic Honey (310 kcal, 22g Protein, 25g Carbs, 14g Fat)\n• Dinner (8:00 PM): 180g Herb-Roasted Chicken Thigh (skinless), 200g Roasted Tri-Color Fingerling Potatoes, 150g Sautéed Garlic Broccolini with Olive Oil (600 kcal, 44g Protein, 58g Carbs, 20g Fat)\n• Daily Hydration Target: 3.5 Liters Water + 2 cups Green Tea (EGCG Polyphenols)"
        )
        db.session.add_all([meal1, meal2, meal3])

        fb1 = Feedback(
            user_id=member1.id,
            trainer_id=profile_sarah.id,
            rating=5,
            review_text="Sarah is an exceptional coach! Her cueing in Power Yoga has transformed my core strength and hamstring flexibility completely.",
            created_at=local_now() - timedelta(days=4)
        )
        fb2 = Feedback(
            user_id=member2.id,
            trainer_id=profile_tanvir.id,
            rating=5,
            review_text="Tanvir's strength programming is world class. Added 20kg to my deadlift in under 2 months with zero injuries.",
            created_at=local_now() - timedelta(days=2)
        )
        fb3 = Feedback(
            user_id=member3.id,
            trainer_id=profile_farhan.id,
            rating=5,
            review_text="Farhan brings unmatched energy to HIIT classes. The music, intensity, and motivation keep you pushing until the final rep!",
            created_at=local_now() - timedelta(days=1)
        )
        fb4 = Feedback(
            user_id=member1.id,
            class_id=class_yoga1.id,
            rating=5,
            review_text="Power Yoga Flow is the best evening workout in the city. Clean studio, great atmosphere, and wonderful pacing.",
            created_at=local_now() - timedelta(days=3)
        )
        fb5 = Feedback(
            user_id=member2.id,
            class_id=class_strength1.id,
            rating=4,
            review_text="High intensity strength pushes your limits. Great coaching on proper barbell form.",
            created_at=local_now() - timedelta(days=1)
        )
        db.session.add_all([fb1, fb2, fb3, fb4, fb5])

        db.session.commit()
        print("Database successfully seeded with all 10 features and evidence-based nutrition plans!")

if __name__ == '__main__':
    seed_database()
