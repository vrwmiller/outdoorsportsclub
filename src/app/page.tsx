import LoginButton from "@/components/LoginButton";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl shadow-md p-10 text-center max-w-md w-full">
        <h1 className="text-3xl font-bold text-gray-800 mb-2">
          Outdoor Sports Club
        </h1>
        <p className="text-gray-500 text-sm mb-8">
          Members — sign in to access the portal.
        </p>
        <LoginButton />
      </div>
    </main>
  );
}
