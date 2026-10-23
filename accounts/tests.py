from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

PASSWORD = "Gizli-Parola-482"


def register_data(**overrides):
    data = {
        "email": "ali@example.com",
        "username": "ali_veli",
        "password1": PASSWORD,
        "password2": PASSWORD,
    }
    data.update(overrides)
    return data


class RegisterTests(TestCase):
    def test_successful_registration_logs_in_and_redirects_home(self):
        response = self.client.post(reverse("register"), register_data())
        self.assertRedirects(response, reverse("home"))
        user = User.objects.get()
        self.assertEqual(user.email, "ali@example.com")
        self.assertEqual(user.username, "ali_veli")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_email_and_username_are_stored_lowercase(self):
        self.client.post(
            reverse("register"),
            register_data(email="Ali@Example.COM", username="Ali.Veli"),
        )
        user = User.objects.get()
        self.assertEqual(user.email, "ali@example.com")
        self.assertEqual(user.username, "ali.veli")

    def test_duplicate_email_rejected_case_insensitive(self):
        User.objects.create_user("ali@example.com", "ilk", PASSWORD)
        response = self.client.post(
            reverse("register"), register_data(email="ALI@example.com", username="ikinci")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "email", "Bu e-posta adresi zaten kayıtlı.")
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_username_rejected_case_insensitive(self):
        User.objects.create_user("ilk@example.com", "ali_veli", PASSWORD)
        response = self.client.post(
            reverse("register"), register_data(email="yeni@example.com", username="ALI_Veli")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "username", "Bu kullanıcı adı zaten alınmış.")
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_usernames_rejected(self):
        for username in ["ab", "Ali Veli", "admin", "ADMIN", "yonetim", "a" * 21, "ali-veli", "çağrı", "ali@veli"]:
            with self.subTest(username=username):
                response = self.client.post(reverse("register"), register_data(username=username))
                self.assertEqual(response.status_code, 200)
                self.assertIn("username", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)

    def test_valid_usernames_accepted(self):
        for index, username in enumerate(["abc", "a.b_c9", "a" * 20]):
            with self.subTest(username=username):
                self.client.post(
                    reverse("register"),
                    register_data(email=f"k{index}@example.com", username=username),
                )
                self.assertTrue(User.objects.filter(username=username).exists())
                self.client.post(reverse("logout"))

    def test_password_mismatch_rejected(self):
        response = self.client.post(reverse("register"), register_data(password2="Baska-Parola-1"))
        self.assertFormError(response.context["form"], "password2", "Parolalar eşleşmiyor.")
        self.assertEqual(User.objects.count(), 0)

    def test_weak_password_rejected(self):
        response = self.client.post(
            reverse("register"), register_data(password1="12345678", password2="12345678")
        )
        self.assertIn("password1", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)

    def test_invalid_email_rejected(self):
        response = self.client.post(reverse("register"), register_data(email="gecersiz"))
        self.assertIn("email", response.context["form"].errors)

    def test_authenticated_user_is_redirected_from_register(self):
        User.objects.create_user("ali@example.com", "ali", PASSWORD)
        self.client.login(email="ali@example.com", password=PASSWORD)
        self.assertRedirects(self.client.get(reverse("register")), reverse("home"))


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ali@example.com", "ali", PASSWORD)

    def test_login_with_email_and_password(self):
        response = self.client.post(
            reverse("login"), {"username": "ali@example.com", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_email_is_case_insensitive(self):
        response = self.client.post(
            reverse("login"), {"username": "  ALI@Example.com ", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("home"))

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(
            reverse("login"), {"username": "ali@example.com", "password": "yanlis"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "E-posta veya parola hatalı.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_with_username_instead_of_email_fails(self):
        response = self.client.post(reverse("login"), {"username": "ali", "password": PASSWORD})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(response.status_code, 200)

    def test_login_respects_next_parameter(self):
        response = self.client.post(
            reverse("login") + "?next=/anket/olustur/",
            {"username": "ali@example.com", "password": PASSWORD, "next": "/anket/olustur/"},
        )
        self.assertRedirects(response, "/anket/olustur/", fetch_redirect_response=False)

    def test_login_ignores_external_next_parameter(self):
        response = self.client.post(
            reverse("login"),
            {"username": "ali@example.com", "password": PASSWORD, "next": "https://kotu.example/"},
        )
        self.assertRedirects(response, reverse("home"))

    def test_login_page_keeps_next_in_form(self):
        response = self.client.get(reverse("login") + "?next=/anket/olustur/")
        self.assertContains(response, 'name="next" value="/anket/olustur/"')

    def test_authenticated_user_is_redirected_from_login(self):
        self.client.login(email="ali@example.com", password=PASSWORD)
        self.assertRedirects(self.client.get(reverse("login")), reverse("home"))

    def test_logout_requires_post(self):
        self.client.login(email="ali@example.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_post_logs_out(self):
        self.client.login(email="ali@example.com", password=PASSWORD)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)


class NavbarTests(TestCase):
    def test_guest_navbar(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Giriş yap")
        self.assertContains(response, "Kayıt ol")
        self.assertNotContains(response, "Çıkış")

    def test_member_navbar_shows_username_but_never_email(self):
        User.objects.create_user("gizli.mail@example.com", "ali", PASSWORD)
        self.client.login(email="gizli.mail@example.com", password=PASSWORD)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "@ali")
        self.assertContains(response, "Çıkış")
        self.assertContains(response, "+ Anket oluştur")
        self.assertNotContains(response, "Kayıt ol")
        self.assertNotContains(response, "gizli.mail@example.com")
