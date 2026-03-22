// register.js
document.addEventListener('DOMContentLoaded', () => {
    const registerForm = document.getElementById('registerForm');
    const messageDiv = document.getElementById('message');

    if (registerForm) {
        registerForm.addEventListener('submit', async (event) => {
            event.preventDefault(); // Prevent default form submission

            const username = registerForm.username.value;
            const password = registerForm.password.value;

            try {
                const response = await fetch('/register', {
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
                        window.location.href = '/login'; // Redirect to login on successful registration
                    }, 2000); // Give user time to read message
                } else {
                    messageDiv.textContent = data.message;
                    messageDiv.className = 'mt-6 text-center text-lg font-medium text-red-600';
                }
            } catch (error) {
                console.error('Registration error:', error);
                messageDiv.textContent = 'An error occurred during registration. Please try again.';
                messageDiv.className = 'mt-6 text-center text-lg font-medium text-red-600';
            }
        });
    }
});
