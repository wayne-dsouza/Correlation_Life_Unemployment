import pandas as pd
import matplotlib.pyplot as plt
import mplcursors

# Adjust pandas display options to show all rows
pd.set_option('display.max_rows', None)

# Read the data from the Excel sheets
df1 = pd.read_excel(r'C:\python\CSV\unemployment_plot.xlsx', sheet_name='Sheet1')
df2 = pd.read_excel(r'C:\python\CSV\unemployment_plot.xlsx', sheet_name='Sheet2')
df3 = pd.read_excel(r'C:\python\CSV\unemployment_plot.xlsx', sheet_name='Sheet3')

# Merge the dataframes based on the 'country' column
merged_df = pd.merge(df1, df2, on='country')
merged_df = pd.merge(merged_df, df3, on='country')

# Drop rows with missing values
merged_df.dropna(inplace=True)

# Specify the actual column names
unemployment_column = 'unemployment'  # Replace with the actual column name in Sheet1
life_expectancy_column = 'life_expectancy'  # Replace with the actual column name in Sheet2
population_column = 'population'  # Replace with the actual column name in Sheet3

# Convert population column to numerical values
def convert_population(population):
    if population.endswith('M'):
        return float(population[:-1]) * 1000000
    elif population.endswith('k'):
        return float(population[:-1]) * 1000
    else:
        return float(population)

# Apply the conversion function to the population column
merged_df[population_column] = merged_df[population_column].apply(convert_population)

# Create a new dataframe with the desired columns
database = merged_df[['country', unemployment_column, life_expectancy_column, population_column]]

# Reset the index of the database DataFrame
database.reset_index(drop=True, inplace=True)

# Print the resulting database
print(database)

# Create the scatter plot
scatter = plt.scatter(database[unemployment_column] * 100, database[life_expectancy_column], s=database[population_column] / 100000, alpha=0.6)

# Create tooltips for scatter plot points
tooltips = mplcursors.cursor(scatter).connect(
    "add", lambda sel: sel.annotation.set_text(f"{database['country'][sel.target.index]}\nPopulation: {database['population'][sel.target.index]:,.0f}")
)

# Set labels and title for the plot
plt.xlabel('Unemployment Rate (%)')
plt.ylabel('Life Expectancy')
plt.title('Unemployment Rate vs. Life Expectancy')

# Set logarithmic scale on the x-axis
plt.xscale('log')

# Show the plot
plt.show()
