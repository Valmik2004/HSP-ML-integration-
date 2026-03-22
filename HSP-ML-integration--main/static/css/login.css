// login.js
document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('loginForm');
    const messageDiv = document.getElementById('message');

    if (loginForm) {
        loginForm.addEventListener('submit', async (event) => {
            event.preventDefault(); // Prevent default form submission

            const username = loginForm.username.value;
            const password = loginForm.password.value;

            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded', // For form data
                    },
                    body: new URLSearchParams({
                        username: username,
                        password: password
                    })
                });

                const data = await response.json();

                if (data.success) {
                    messageDiv.textContent = data.message;
                    messageDiv.className = 'mt-6 text-center text-lg font-medium text-green-600';
                    setTimeout(() => {
                        window.location.href = '/dashboard'; // Redirect to dashboard on success
                    }, 1000);
                } else {
                    messageDiv.textContent = data.message;
                    messageDiv.className = 'mt-6 text-center text-lg font-medium text-red-600';
                }
            } catch (error) {
                console.error('Login error:', error);
                messageDiv.textContent = 'An error occurred during login. Please try again.';
                messageDiv.className = 'mt-6 text-center text-lg font-medium text-red-600';
            }
        });
    }
});
